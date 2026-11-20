import itertools

import numpy as np
import pytest

from apthmm import hmm


@pytest.fixture
def modelo():
    A = np.array([[0.7, 0.3], [0.4, 0.6]])
    B = np.array([[0.5, 0.4, 0.1], [0.1, 0.3, 0.6]])
    pi = np.array([0.6, 0.4])
    return hmm.HMM(A, B, pi)


def _conjunta(m, q, o):
    p = m.pi[q[0]] * m.B[q[0], o[0]]
    for t in range(1, len(o)):
        p *= m.A[q[t - 1], q[t]] * m.B[q[t], o[t]]
    return p


def test_filtrado_igual_a_fuerza_bruta(modelo):
    o = np.array([0, 2, 1])
    alfa, ll = modelo.filtrar(o)
    total = sum(_conjunta(modelo, q, o) for q in itertools.product(range(2), repeat=3))
    assert np.isclose(ll, np.log(total))
    for t in range(3):
        marg = np.zeros(2)
        for q in itertools.product(range(2), repeat=t + 1):
            marg[q[-1]] += _conjunta(modelo, q, o[: t + 1])
        assert np.allclose(alfa[t], marg / marg.sum())


def test_viterbi_igual_a_fuerza_bruta(modelo):
    o = np.array([0, 2, 2, 1])
    mejor = max(itertools.product(range(2), repeat=4), key=lambda q: _conjunta(modelo, q, o))
    assert tuple(modelo.viterbi(o)) == mejor


def test_supervisado_cuenta_y_suaviza():
    obs = [np.array([0, 0, 1, 2])]
    est = [np.array([0, 0, 1, 1])]
    m = hmm.HMM.supervisado(obs, est, N=2, M=3, alfa_A=0, alfa_B=0, alfa_pi=0)
    assert np.allclose(m.A, [[0.5, 0.5], [0, 1]])
    assert np.allclose(m.B, [[1, 0, 0], [0, 0.5, 0.5]])
    assert np.allclose(m.pi, [1, 0])
    m2 = hmm.HMM.supervisado(obs, est, N=2, M=3, alfa_B=1)
    assert np.allclose(m2.B[0], np.array([3, 1, 1]) / 5)


def test_mascara_prohibe_solo_saltos_no_vistos_entre_ataques():
    est = [np.array([0, 1, 1, 2, 0, 3])]
    m = hmm.mascara_estructural(est, N=5)
    assert m[1, 2] and m[2, 0] and m[0, 3]          # vistas o desde/hacia benigno
    assert m[4, 4] and m[0, 4] and m[4, 0]          # diagonal y benigno siempre
    assert not m[1, 4] and not m[3, 1] and not m[2, 1]


def test_em_conserva_ceros_estructurales():
    rng = np.random.default_rng(0)
    est = [np.repeat(rng.integers(0, 3, 40), 5) for _ in range(5)]
    est = [np.where(q == 2, 1, q) for q in est]           # nunca 0->2 ni 2->x
    est[0][-5:] = 2
    obs = [np.clip(q + rng.integers(0, 2, len(q)), 0, 3) for q in est]
    mascara = hmm.mascara_estructural(est, N=3)
    m0 = hmm.HMM.supervisado(obs, est, 3, 4, alfa_B=0.1, mascara=mascara)
    m1, historia = hmm.refinar_em(m0, obs, obs, mascara, alfa_B=0.1, max_iter=5)
    assert len(historia) >= 2
    assert np.all(m1.A[~mascara] == 0)
    assert np.allclose(m1.A.sum(1), 1) and np.allclose(m1.B.sum(1), 1)


def test_asignacion_hungara_recupera_permutacion():
    real = np.array([0, 0, 1, 1, 2, 2, 2])
    pred = np.array([2, 2, 0, 0, 1, 1, 0])
    perm = hmm.asignacion_hungara(pred, real, 3)
    assert list(perm) == [1, 2, 0]
    m = hmm.HMM(np.eye(3), np.eye(3), np.array([0.2, 0.3, 0.5]))
    mp = hmm.permutar(m, perm)
    # Estado aprendido k pasa a la etapa perm[k]: la etapa 0 era el estado 2 (pi = 0,5).
    assert np.allclose(mp.pi, [0.5, 0.2, 0.3])
    assert np.allclose(mp.B[0], m.B[2])
