"""Extrae, para cada estudio de la tabla de hallazgos, las métricas mencionadas en el
resumen (campo abstract de referencias.bib) y el primer valor numérico asociado.

Se usó una sola vez para crear hallazgos.json a partir de la tabla original (formato
de texto) de 6-EstadoArte.tex, que ya no existe. Se conserva como registro del
procedimiento. NO volver a ejecutarlo sobre hallazgos.json: sobrescribiría las
correcciones posteriores (Baksi y Upadhyaya sin DARPA, Y. Javed et al. con CICIDS).
Los valores de métricas que la extracción asoció mal se corrigen en MANUAL de
gen_hallazgos.py."""
import re, sys, json

tex = open(sys.argv[1], encoding='utf-8').read()
bib = open(sys.argv[2], encoding='utf-8').read()

ini = tex.index('\\label{tab:hallazgos}')
fin = tex.index('\\end{xltabular}', ini)
filas = []
for line in tex[ini:fin].splitlines():
    m = re.match(r'(.*?)\\parencite\{([^}]+)\}\s*&\s*(\d{4})\s*&(.*?)&(.*?)&(.*?)\\\\', line)
    if m:
        filas.append(dict(nombre=m.group(1).strip(), key=m.group(2), anio=m.group(3),
                          modelos=[x.strip() for x in m.group(4).split(',') if x.strip()],
                          datos=[x.strip() for x in m.group(5).split(',') if x.strip()],
                          desb=m.group(6).strip()))

def abstract(key):
    i = bib.find('{' + key + ',')
    if i < 0:
        return None
    j = bib.find('\n@', i)
    ent = bib[i: j if j > 0 else None]
    m = re.search(r'abstract\s*=\s*\{(.*?)\},\s*\n\s*\w+\s*=', ent, re.S)
    return m.group(1) if m else ''

PATS = {
    'Accuracy': r'accura(?:cy|cies)',
    'Precision': r'precision',
    'Recall': r'recall',
    'F1': r'f1|f-1|f-score|f-measure|f1-score',
    'AUC': r'\bauc\b|\broc\b',
}
NUM = r'(\d{1,3}(?:\.\d+)?)\s*(?:\\?%|percent)'

res = []
for f in filas:
    a = abstract(f['key'])
    a2 = re.sub(r'[{}]', '', a or '')
    met = {}
    for k, p in PATS.items():
        for mm in re.finditer(p, a2, re.I):
            ventana = a2[max(0, mm.start() - 60): mm.end() + 60]
            val = re.search(NUM, a2[mm.end(): mm.end() + 60]) or re.search(NUM, a2[max(0, mm.start() - 40): mm.start()])
            met.setdefault(k, val.group(1) + '%' if val else 'x')
            if val:
                met[k] = val.group(1) + '%'
                break
    f['metricas'] = met
    f['abstract_ok'] = a is not None and a != ''
    res.append(f)

json.dump(res, open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
c = Counter(k for f in res for k in f['metricas'])
print('estudios', len(res), 'sin abstract', sum(not f['abstract_ok'] for f in res))
print(dict(c))
for f in res:
    if f['metricas']:
        print(f['key'], f['metricas'])
