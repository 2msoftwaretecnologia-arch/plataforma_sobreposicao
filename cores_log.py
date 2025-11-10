import sys

try:
    # Habilita códigos ANSI no Windows para cores no terminal
    from colorama import init as _colorama_init  # type: ignore
    _colorama_init(autoreset=True)
except Exception:
    # Se colorama não estiver disponível, os códigos ANSI ainda funcionarão
    # na maioria dos terminais modernos.
    pass

# Mapa de cores suportadas para foreground (texto)
COLOR_CODES = {
    # Cores "escuras" (intensidade normal)
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",

    # Alias para tons escuros explícitos
    "dark_red": "31",
    "dark_green": "32",
    "dark_yellow": "33",
    "dark_blue": "34",
    "dark_magenta": "35",
    "dark_cyan": "36",
    "dark_white": "37",
    "grey": "90",

    # Tons brilhantes
    "bright_black": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
    "bright_white": "97",
}

STYLE_CODES = {
    "bold": "1",
    "dim": "2",
    "underline": "4",
    "reverse": "7",
}

RESET = "\033[0m"

def _ansi_sequence(color_code: str, styles=None) -> str:
    parts = []
    if styles:
        if isinstance(styles, str):
            styles = [styles]
        for s in styles:
            code = STYLE_CODES.get(str(s).lower())
            if code:
                parts.append(code)
    parts.append(color_code)
    return "\033[" + ";".join(parts) + "m"

def color_print(text: str,
                color: str = "white",
                style=None,
                prefix: str | None = None,
                end: str = "\n",
                file = sys.stdout) -> None:
    """Imprime texto na cor desejada.

    Parâmetros:
    - text: conteúdo a imprimir
    - color: nome da cor (ex.: 'red', 'bright_green', 'dark_yellow')
    - style: estilo opcional ('bold', 'dim', 'underline', ...). Pode ser str ou lista.
    - prefix: texto opcional para prefixar a mensagem
    - end: terminador (padrão '\n')
    - file: destino (padrão stdout)
    """
    color_code = COLOR_CODES.get(str(color).lower(), COLOR_CODES["white"])
    start = _ansi_sequence(color_code, styles=style)
    msg = f"{prefix + ' ' if prefix else ''}{text}"
    try:
        file.write(f"{start}{msg}{RESET}{end}")
        try:
            file.flush()
        except Exception:
            pass
    except Exception:
        # Fallback simples caso o terminal não aceite ANSI
        print(msg, end=end, flush=True)

def log_print(message: str,
              level: str = "INFO",
              system: str = "VERIFICADOR") -> None:
    """Imprime mensagem com cor baseada no nível de severidade.

    Níveis suportados: 'ERROR', 'WARNING', 'INFO', 'SUCCESS', 'DEBUG'.
    - Mensagens mais graves (ERROR/WARNING) usam tons escuros.
    - Mensagens menos graves usam tons mais claros/brilhantes.
    """
    lvl = str(level).upper()
    mapping = {
        "ERROR": ("dark_red", None),       # mais escuro
        "WARNING": ("dark_yellow", None),  # mais escuro
        "INFO": ("bright_white", None),
        "SUCCESS": ("bright_green", None),
        "DEBUG": ("bright_cyan", "dim"),
    }
    color, style = mapping.get(lvl, ("bright_white", None))
    prefix = f"[{system}]"
    color_print(message, color=color, style=style, prefix=prefix)