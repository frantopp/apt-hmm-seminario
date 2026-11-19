# Makefile — compila el informe LaTeX con latexmk (pdfLaTeX + biber).
# Misma idea que portuaria-organizacion: la salida queda en build/, nunca
# junto a los .tex.
#
# Uso (desde la raíz del repo, en Git Bash o PowerShell):
#   make            # = make informe
#   make informe    # compila informe/main.tex -> build/informe/main.pdf
#   make watch      # recompila solo cada vez que guardas (Ctrl+C para salir)
#   make clean      # borra auxiliares y PDF de build/informe
#
# -r informe/.latexmkrc: latexmk lee el .latexmkrc de la carpeta donde se
# ejecuta ANTES de hacer -cd, así que hay que pasárselo explícito.
#
# Las recetas no usan comandos de sh (mkdir, rm), así que funcionan con el
# make de scoop tanto en Git Bash como en PowerShell: latexmk crea y limpia
# la carpeta de salida él mismo.

BUILD   := $(CURDIR)/build
LATEXMK := latexmk -r informe/.latexmkrc -cd -pdf -interaction=nonstopmode -halt-on-error -file-line-error

.PHONY: all informe watch clean

all: informe

informe:
	$(LATEXMK) -output-directory="$(BUILD)/informe" informe/main.tex

watch:
	$(LATEXMK) -pvc -view=none -output-directory="$(BUILD)/informe" informe/main.tex

clean:
	latexmk -r informe/.latexmkrc -cd -C -output-directory="$(BUILD)/informe" informe/main.tex
