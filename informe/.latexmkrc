# Configuración de latexmk para informe/ (la usan `make` y el editor).
#
# - pdfLaTeX como motor; latexmk detecta biblatex y corre biber solo.
# - Regla para glossaries: corre makeglossaries cuando el glosario cambia.
#   Necesita Perl (Strawberry Perl: `scoop install perl`).

$pdf_mode = 1;
$bibtex_use = 2;   # corre biber cuando hace falta y limpia sus archivos con -C

# main.tex usa \include{Portadas/...} y \include{seccion/...}: pdfLaTeX escribe
# un .aux por archivo incluido dentro de la carpeta de salida (build/informe)
# y falla si esas subcarpetas no existen ("I can't write on file ...aux").
# Antes de cada pasada se replican en la salida las subcarpetas de informe/.
use File::Find qw(find);
use File::Path qw(make_path);

$pdflatex = 'internal pdflatex_con_carpetas %O %S';

sub pdflatex_con_carpetas {
  my $salida = $aux_dir || $out_dir;
  if ($salida && $salida ne '.') {
    find({ no_chdir => 1, wanted => sub {
      return unless -d $_;
      (my $rel = $_) =~ s{^\.[\/\\]?}{};
      return if $rel eq '';
      if ($rel =~ /(^|[\/\\])\./) { $File::Find::prune = 1; return; }  # ocultas
      make_path("$salida/$rel");
    }}, '.');
  }
  return system('pdflatex', @_);
}

add_cus_dep('glo', 'gls', 0, 'run_makeglossaries');
add_cus_dep('acn', 'acr', 0, 'run_makeglossaries');

sub run_makeglossaries {
  my ($base_name, $path) = fileparse($_[0]);
  my @args = ('-q', $base_name);
  unshift @args, '-d', $path if $path;
  return system('makeglossaries', @args);
}

push @generated_exts, 'glo', 'gls', 'glg', 'acn', 'acr', 'alg', 'ist',
                      'nlo', 'nls', 'nlg', 'run.xml', 'bcf';
