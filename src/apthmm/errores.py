"""Errores propios del motor. La línea de comandos los muestra sin traza y con una pista."""


class ErrorApthmm(Exception):
    """Base de los errores esperables (configuración o datos), no de los defectos del código."""


class ErrorConfiguracion(ErrorApthmm):
    """Parámetro inválido, archivo de configuración mal formado o combinación incoherente."""


class ErrorDatos(ErrorApthmm):
    """Archivos ausentes o con un formato distinto del esperado, o particiones vacías."""
