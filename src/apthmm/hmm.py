"""HMM discreto λ = (A, B, π): estimación supervisada, filtrado, Viterbi y EM restringido.

La estimación por conteo, el filtrado (forward escalado) y Viterbi son propios. Para
Baum-Welch se usa hmmlearn (implementación en C), inicializado con nuestros parámetros:
la reestimación conserva los ceros de A cuando su pseudoconteo a priori también es cero.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from . import config

log = logging.getLogger(__name__)
logging.getLogger("hmmlearn").setLevel(logging.ERROR)


PISO = 1e-300


def _normalizar(x: np.ndarray, eje: int = -1) -> np.ndarray:
    s = x.sum(axis=eje, keepdims=True)
    s[s == 0] = 1.0
    return x / s


def mascara_estructural(estados: list[np.ndarray], N: int = config.N_ESTADOS) -> np.ndarray:
    """D9: se prohíbe una transición entre dos estados de ataque no vista en entrenamiento.

    Siempre se permiten la permanencia (i -> i) y las transiciones desde y hacia benigno.
    """
    vistas = np.zeros((N, N), bool)
    for q in estados:
        if len(q) > 1:
            vistas[q[:-1], q[1:]] = True
    permitida = vistas.copy()
    permitida[config.BENIGNO, :] = True
    permitida[:, config.BENIGNO] = True
    np.fill_diagonal(permitida, True)
    return permitida


@dataclass
class HMM:
    A: np.ndarray   # (N, N)
    B: np.ndarray   # (N, M)
    pi: np.ndarray  # (N,)

    @property
    def N(self) -> int:
        return self.A.shape[0]

    @property
    def M(self) -> int:
        return self.B.shape[1]

    # ------------------------------------------------------------ estimación
    @classmethod
    def supervisado(cls, obs: list[np.ndarray], estados: list[np.ndarray], N: int, M: int,
                    alfa_A: float = config.ALFA_A, alfa_B: float = 0.1, alfa_pi: float = config.ALFA_PI,
                    mascara: np.ndarray | None = None, pesos: list[float] | None = None) -> "HMM":
        """Máxima verosimilitud por conteo con suavizado aditivo (Laplace si alfa = 1)."""
        if len(obs) != len(estados) or any(len(o) != len(q) for o, q in zip(obs, estados)):
            raise ValueError("obs y estados deben tener las mismas secuencias y largos")
        if min(alfa_A, alfa_B, alfa_pi) < 0:
            raise ValueError("Los suavizados no pueden ser negativos")
        pesos = [1.0] * len(obs) if pesos is None else list(pesos)
        if len(pesos) != len(obs):
            raise ValueError("Hace falta un peso por secuencia")
        cA, cB, cpi = np.zeros((N, N)), np.zeros((N, M)), np.zeros(N)
        for o, q, p in zip(obs, estados, pesos):
            if len(q) == 0:
                continue
            if q.min() < 0 or q.max() >= N or o.min() < 0 or o.max() >= M:
                raise ValueError(f"Estados fuera de [0, {N}) o símbolos fuera de [0, {M})")
            cpi[q[0]] += p
            np.add.at(cA, (q[:-1], q[1:]), p)
            np.add.at(cB, (q, o), p)
        mascara = np.ones((N, N), bool) if mascara is None else mascara
        A = np.where(mascara, cA + alfa_A, 0.0)
        return cls(_normalizar(A), _normalizar(cB + alfa_B), _normalizar(cpi + alfa_pi))

    # ------------------------------------------------------------ inferencia
    def filtrar(self, o: np.ndarray) -> tuple[np.ndarray, float]:
        """Probabilidad filtrada P(q_t | O_1..O_t) para cada t, y log P(O | λ).

        Si un símbolo tiene probabilidad cero en todos los estados alcanzables (solo puede
        pasar con emisiones sin suavizar), se conserva la predicción a priori en vez de
        dividir por cero, y se suma log(PISO) a la verosimilitud.
        """
        T = len(o)
        alfa = np.empty((T, self.N))
        if T == 0:
            return alfa, 0.0
        Bo = self.B[:, o].T
        loglik = 0.0
        prior = self.pi
        for t in range(T):
            if t:
                prior = alfa[t - 1] @ self.A
            a = prior * Bo[t]
            c = a.sum()
            if not c > PISO:
                a, c = prior, PISO
                s = a.sum()
                a = a / s if s > 0 else np.full(self.N, 1.0 / self.N)
                alfa[t] = a
                loglik += np.log(c)
                continue
            loglik += np.log(c)
            alfa[t] = a / c
        return alfa, float(loglik)

    def viterbi(self, o: np.ndarray) -> np.ndarray:
        """Secuencia de estados más probable Q* (reconstrucción retrospectiva)."""
        with np.errstate(divide="ignore"):
            lA, lB, lpi = np.log(self.A), np.log(self.B), np.log(self.pi)
        T = len(o)
        if T == 0:
            return np.empty(0, dtype=np.int64)
        psi = np.empty((T, self.N), dtype=np.int16)
        d = lpi + lB[:, o[0]]
        for t in range(1, T):
            m = d[:, None] + lA
            psi[t] = m.argmax(axis=0)
            d = m.max(axis=0) + lB[:, o[t]]
        q = np.empty(T, dtype=np.int64)
        q[-1] = int(d.argmax())
        for t in range(T - 1, 0, -1):
            q[t - 1] = psi[t, q[t]]
        return q

    def loglik(self, obs: list[np.ndarray]) -> float:
        return sum(self.filtrar(o)[1] for o in obs if len(o))

    # ------------------------------------------------------------ hmmlearn
    def _a_hmmlearn(self, **kw):
        from hmmlearn.hmm import CategoricalHMM
        m = CategoricalHMM(n_components=self.N, n_features=self.M, init_params="", params="ste", **kw)
        m.startprob_, m.transmat_, m.emissionprob_ = self.pi.copy(), self.A.copy(), self.B.copy()
        return m


def _apilar(obs: list[np.ndarray]):
    obs = [o for o in obs if len(o)]
    if not obs:
        raise ValueError("No hay secuencias con observaciones")
    return np.concatenate(obs).reshape(-1, 1), [len(o) for o in obs]


def _valido(m) -> bool:
    return all(np.isfinite(x).all() for x in (m.transmat_, m.emissionprob_, m.startprob_))


def refinar_em(modelo: HMM, obs: list[np.ndarray], obs_val: list[np.ndarray], mascara: np.ndarray,
               alfa_A: float = config.ALFA_A, alfa_B: float = 0.1, alfa_pi: float = config.ALFA_PI,
               max_iter: int = 50, paciencia: int = 2) -> tuple[HMM, list[dict]]:
    """D10: Baum-Welch desde la estimación supervisada, con ceros de A fijos y
    detención cuando la log-verosimilitud de validación baja `paciencia` veces seguidas."""
    X, L = _apilar(obs)
    Xv, Lv = _apilar(obs_val)
    m = modelo._a_hmmlearn(
        n_iter=1, tol=0.0,
        transmat_prior=1.0 + alfa_A * mascara,   # prior 1 (sin pseudoconteo) donde hay cero estructural
        emissionprob_prior=1.0 + alfa_B, startprob_prior=1.0 + alfa_pi,
    )
    mejor = HMM(modelo.A.copy(), modelo.B.copy(), modelo.pi.copy())
    mejor_val = m.score(Xv, Lv)
    historia = [{"iter": 0, "ll_val": float(mejor_val)}]
    peor_seguidas = 0
    previo = mejor_val
    for it in range(1, max_iter + 1):
        try:
            m.fit(X, L)
            ll = m.score(Xv, Lv)
        except (ValueError, FloatingPointError) as x:
            log.warning("Baum-Welch se detuvo en la iteración %d: %s", it, x)
            historia.append({"iter": it, "error": str(x)})
            break
        if not (_valido(m) and np.isfinite(ll)):
            log.warning("Baum-Welch produjo parámetros no finitos en la iteración %d: se conserva el mejor previo", it)
            historia.append({"iter": it, "error": "parámetros no finitos"})
            break
        historia.append({"iter": it, "ll_val": float(ll)})
        if ll > mejor_val:
            mejor_val = ll
            mejor = HMM(m.transmat_.copy(), m.emissionprob_.copy(), m.startprob_.copy())
        peor_seguidas = peor_seguidas + 1 if ll < previo else 0
        previo = ll
        if peor_seguidas >= paciencia:
            break
    return mejor, historia


def no_supervisado(obs: list[np.ndarray], N: int, M: int, semillas=range(10), max_iter: int = 100,
                   alfa_B: float = 0.1) -> tuple[HMM, list[float]]:
    """H0: Baum-Welch desde inicializaciones aleatorias, se queda el de mayor verosimilitud."""
    from hmmlearn.hmm import CategoricalHMM
    X, L = _apilar(obs)
    mejor, mejor_ll, lls = None, -np.inf, []
    for s in semillas:
        m = CategoricalHMM(n_components=N, n_features=M, n_iter=max_iter, tol=1e-3,
                           random_state=int(s), init_params="ste", params="ste",
                           emissionprob_prior=1.0 + alfa_B)
        try:
            m.fit(X, L)
            ll = m.score(X, L)
        except (ValueError, FloatingPointError) as x:
            log.warning("H0: el reinicio con semilla %s falló: %s", s, x)
            lls.append(float("nan"))
            continue
        if not (_valido(m) and np.isfinite(ll)):
            log.warning("H0: el reinicio con semilla %s dio parámetros no finitos", s)
            lls.append(float("nan"))
            continue
        lls.append(float(ll))
        if ll > mejor_ll:
            mejor_ll, mejor = ll, HMM(m.transmat_.copy(), m.emissionprob_.copy(), m.startprob_.copy())
    if mejor is None:
        raise RuntimeError("H0: fallaron todos los reinicios de Baum-Welch")
    return mejor, lls


def asignacion_hungara(pred: np.ndarray, real: np.ndarray, N: int) -> np.ndarray:
    """Permutación estado aprendido -> etapa que maximiza las coincidencias."""
    C = np.zeros((N, N))
    np.add.at(C, (pred, real), 1)
    filas, cols = linear_sum_assignment(-C)
    perm = np.empty(N, dtype=np.int64)
    perm[filas] = cols
    return perm


def permutar(modelo: HMM, perm: np.ndarray) -> HMM:
    """Reordena los estados para que el estado k pase a ser la etapa perm[k]."""
    inv = np.argsort(perm)
    return HMM(modelo.A[np.ix_(inv, inv)], modelo.B[inv], modelo.pi[inv])
