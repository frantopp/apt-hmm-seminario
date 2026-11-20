"""Genera informe/seccion/tablas/hallazgos.tex (Tabla 6.1) a partir de hallazgos.json.

hallazgos.json es la fuente de datos de la tabla: una entrada por estudio del corpus con
sus modelos, conjuntos de datos, desbalance y métricas (estas últimas extraídas de los
resúmenes de referencias.bib con metricas.py). Para corregir un estudio, edita el JSON
(o el diccionario MANUAL de abajo, para valores de métricas) y vuelve a generar.

Uso, desde la raíz del repo:
    python scripts/tabla_hallazgos/gen_hallazgos.py scripts/tabla_hallazgos/hallazgos.json \\
        informe/seccion/6-EstadoArte.tex informe/seccion/tablas/hallazgos.tex

La primera vez reemplazó la tabla antigua de 6-EstadoArte.tex por un \\input; ahora solo
reescribe tablas/hallazgos.tex e imprime los totales por columna para contrastarlos con
las figuras del Capítulo 6."""
import json, sys, os, re

js, sec, out = sys.argv[1], sys.argv[2], sys.argv[3]
filas = json.load(open(js, encoding='utf-8'))

# Valores verificados manualmente contra el resumen (las asociaciones automáticas
# tomaban a veces el número de la métrica anterior). x = mencionada sin valor.
MANUAL = {
    'acikgozoglu_explainable_2026': {'Accuracy': '99,06', 'Precision': '95,89', 'Recall': '96,26', 'F1': '96,07'},
    'holbl_machine_2026': {'Accuracy': 'x', 'AUC': None},
    'p_firdani_multi-layer_2026': {'Accuracy': '100'},
    'r_huang_efficient_2026': {'Accuracy': '98,8', 'Recall': '97,0'},
    'salah_dual-model_2026': {'AUC': '0,907'},
    'shahzad_autonomous_2026': {'Accuracy': '95,4', 'Precision': '93,6', 'Recall': '94,7', 'F1': '94,1'},
    'kumari_prospective_2023': {'Accuracy': '94,47'},
    'smiliotopoulos_detection_2023': {'AUC': '0,998'},
    'ghafir2019hmm': {'Accuracy': '91,80'},
}

MODELOS = ['HMM', 'Markov', 'Bayes', 'Grafos', 'Deep L.', 'ML clás.', 'LLM', 'Juegos']
MOD_TIT = ['HMM', 'Markov', 'Bayes', 'Grafos', 'Aprendizaje prof.', 'ML clásico', 'LLM', 'Juegos']
DATOS = [('DAPT2020', {'DAPT2020'}), ('Unraveled', {'Unraveled'}), ('DARPA / OpTC', {'DARPA', 'OpTC'}),
         ('CICAPT-IIoT', {'CICAPT'}), ('CICIDS', {'CICIDS'}), ('NSL-KDD', {'NSL-KDD'}),
         ('UNSW-NB15', {'UNSW'}), ('ToN-IoT', {'ToN-IoT'}), ('KDD99', {'KDD99'})]
METS = [('Accuracy', 'Accuracy (\\%)'), ('Precision', 'Precisión (\\%)'), ('Recall', 'Exhaustividad (\\%)'),
        ('F1', '$F_1$-score (\\%)'), ('AUC', 'AUC')]

def norm(v):
    if v is None or v == 'x':
        return v
    v = v.rstrip('%')
    if '.' in v:
        e, d = v.split('.')
        v = e + ',' + d
    return v

tot = [0] * (len(MODELOS) + len(DATOS) + len(METS) + 1)
lineas = []
for f in filas:
    met = {k: norm(v) for k, v in f['metricas'].items()}
    for k, v in MANUAL.get(f['key'], {}).items():
        if v is None:
            met.pop(k, None)
        else:
            met[k] = v
    celdas = []
    for i, m in enumerate(MODELOS):
        si = m in f['modelos']
        celdas.append('x' if si else '')
        tot[i] += si
    base = len(MODELOS)
    datos = set(f['datos']) - {'--'}
    desconocidos = datos - set().union(*[s for _, s in DATOS])
    if desconocidos:
        sys.exit('dataset sin columna: %s %s' % (f['key'], desconocidos))
    if not datos:
        celdas.append('\\multicolumn{%d}{c|}{\\textit{No aplica}}' % len(DATOS))
    else:
        for j, (_, s) in enumerate(DATOS):
            si = bool(datos & s)
            celdas.append('x' if si else '')
            tot[base + j] += si
    base += len(DATOS)
    for j, (k, _) in enumerate(METS):
        v = met.get(k)
        celdas.append(v if v else '--')
        tot[base + j] += bool(v)
    si = f['desb'] == 'x'
    celdas.append('x' if si else '')
    tot[-1] += si
    lineas.append('\\textcite{%s} & %s \\\\' % (f['key'], ' & '.join(celdas)))

rot = lambda t: '\\rotatebox{90}{%s}' % t
ncol = 1 + len(MODELOS) + len(DATOS) + len(METS) + 1
a, b = 2, 1 + len(MODELOS)
c, d = b + 1, b + len(DATOS)
e, g = d + 1, d + len(METS)
cab = ('\\multicolumn{1}{l|}{} & \\multicolumn{%d}{c|}{\\textbf{Modelos / Técnicas}} & '
       '\\multicolumn{%d}{c|}{\\textbf{Conjuntos de datos}} & \\multicolumn{%d}{c|}{\\textbf{Métricas en el resumen}} & \\\\\n'
       '\\cmidrule(lr){%d-%d}\\cmidrule(lr){%d-%d}\\cmidrule(lr){%d-%d}\n'
       '\\textbf{Estudio}\\rule{0pt}{2.2cm} & %s & %s & %s & %s \\\\\n\\midrule\n') % (
    len(MODELOS), len(DATOS), len(METS), a, b, c, d, e, g,
    ' & '.join(rot(t) for t in MOD_TIT), ' & '.join(rot(t) for t, _ in DATOS),
    ' & '.join(rot(t) for _, t in METS), rot('Desbalance'))

tex = []
tex.append('% Tabla generada a partir de la tabla de hallazgos de la SLR (77 estudios).')
tex.append('% Métricas: valor principal reportado en el resumen; x = mencionada sin valor; -- = no reportada.')
tex.append('\\begin{scriptsize}')
tex.append('\\setlength{\\tabcolsep}{3.2pt}')
tex.append('\\setlength{\\aboverulesep}{0pt}')
tex.append('\\setlength{\\belowrulesep}{0pt}')
tex.append('\\setlength{\\extrarowheight}{1pt}')
tex.append('\\renewcommand{\\arraystretch}{1.1}')
tex.append('\\begin{xltabular}{\\linewidth}{>{\\raggedright\\arraybackslash}X|*{%d}{c}|*{%d}{c}|*{%d}{c}|c}' % (len(MODELOS), len(DATOS), len(METS)))
tex.append('\\caption[Hallazgos por categoría de análisis en los estudios del corpus.]{Hallazgos por categoría de análisis en los estudios del corpus. '
           'En las métricas se indica el valor principal reportado en el resumen; x: métrica mencionada sin valor; --: no reportada. '
           'Fuente: Elaboración propia.}')
tex.append('\\label{tab:hallazgos} \\\\')
tex.append('\\toprule')
tex.append(cab + '\\endfirsthead')
tex.append('\\caption[]{Hallazgos por categoría de análisis en los estudios del corpus (continuación).} \\\\')
tex.append('\\toprule')
tex.append(cab + '\\endhead')
tex.append('\\midrule')
tex.append('\\multicolumn{%d}{r}{\\textit{Continúa en la siguiente página\\dots}} \\\\' % ncol)
tex.append('\\endfoot')
tex.append('\\endlastfoot')
tex.extend(lineas)
tex.append('\\midrule')
tex.append('\\textbf{Total (%d)} & %s \\\\' % (len(filas), ' & '.join('\\textbf{%d}' % t for t in tot)))
tex.append('\\bottomrule')
tex.append('\\end{xltabular}')
tex.append('\\end{scriptsize}')
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w', encoding='utf-8').write('\n'.join(tex) + '\n')

print('totales', dict(zip(MODELOS + [t for t, _ in DATOS] + [k for k, _ in METS] + ['Desb'], tot)))
s = open(sec, encoding='utf-8').read()
if 'tablas/hallazgos' in s:
    sys.exit(0)
i = s.index('\\begin{footnotesize}\n\\setlength{\\tabcolsep}{4pt}\n\\renewcommand{\\arraystretch}{1.15}\n\\begin{xltabular}')
j = s.index('\\end{footnotesize}', i) + len('\\end{footnotesize}')
assert 'tab:hallazgos' in s[i:j]
s = s[:i] + '\\input{seccion/tablas/hallazgos}\n\\FloatBarrier' + s[j:]
open(sec, 'w', encoding='utf-8').write(s)
pass
print('totales', dict(zip(MODELOS + [t for t, _ in DATOS] + [k for k, _ in METS] + ['Desb'], tot)))
