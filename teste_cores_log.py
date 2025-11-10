import io
import importlib
import types
import builtins
import sys
import re

import cores_log as cl


def strip_reset(s: str) -> str:
    # Remove o RESET final para facilitar asserts
    return s.replace(cl.RESET, "")


def test__ansi_sequence_sem_estilo():
    seq = cl._ansi_sequence("31", styles=None)  # vermelho
    assert seq == "\033[31m"


def test__ansi_sequence_com_um_estilo():
    seq = cl._ansi_sequence("32", styles="bold")  # verde + bold
    assert seq == "\033[1;32m"


def test__ansi_sequence_com_varios_estilos():
    seq = cl._ansi_sequence("34", styles=["bold", "underline"])  # azul + bold + underline
    # A ordem esperada é "1;4;34"
    assert seq == "\033[1;4;34m"


def test_color_print_escreve_em_stream():
    buffer = io.StringIO()
    cl.color_print("Ola", color="red", style="bold", prefix="[SYS]", end="", file=buffer)
    out = buffer.getvalue()
    # Deve começar com \033[
    assert out.startswith("\033[")
    # Deve conter a mensagem com prefixo
    assert " [SYS] Ola" in strip_reset(out)


def test_color_print_trata_style_invalido():
    buffer = io.StringIO()
    cl.color_print("Msg", color="green", style="nao_existe", end="", file=buffer)
    out = buffer.getvalue()
    # Sem estilo, apenas cor "32"
    assert out.startswith("\033[32m")
    assert "Msg" in strip_reset(out)


def test_color_print_prefixo_opcional():
    buffer = io.StringIO()
    cl.color_print("Sem prefixo", color="yellow", end="", file=buffer)
    out = buffer.getvalue()
    assert "Sem prefixo" in strip_reset(out)
    assert " [" not in out  # não deve ter o padrão de prefixo


def test_color_print_fallback_quando_write_lanca():
    class BadWriter:
        def write(self, *_):
            raise RuntimeError("falha no write")
        def flush(self):  # pode nem ser chamado
            pass

    # Mesmo se der erro, não deve quebrar; usa print de fallback
    # Captura com io.StringIO via redirect temporário do stdout
    real_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        cl.color_print("Fallback ok", color="red", file=BadWriter())
        out = sys.stdout.getvalue()
        assert "Fallback ok" in out
    finally:
        sys.stdout = real_stdout


def test_log_print_mapeamento_cores_parametrizado():
    casos = {
        "ERROR": "dark_red",
        "WARNING": "dark_yellow",
        "INFO": "bright_white",
        "SUCCESS": "bright_green",
        "DEBUG": "bright_cyan",
    }

    # Monkeypatch simples: intercepta chamadas a color_print
    chamadas = []
    def fake_color_print(text, color, style, prefix, end="\n", file=sys.stdout):
        chamadas.append((text, color, style, prefix))

    # Troca temporariamente a função no módulo
    real_cp = cl.color_print
    try:
        cl.color_print = fake_color_print
        for nivel, cor in casos.items():
            chamadas.clear()
            cl.log_print("mensagem", level=nivel, system="VERIFICADOR")
            assert len(chamadas) == 1
            texto, color, style, prefix = chamadas[0]
            assert texto == "mensagem"
            assert color == cor
            # DEBUG deve ter style 'dim', os demais None
            if nivel == "DEBUG":
                assert style == "dim"
            else:
                assert style is None
            assert prefix == "[VERIFICADOR]"
    finally:
        cl.color_print = real_cp


def test_log_print_nivel_desconhecido_cai_em_bright_white():
    chamadas = []
    def fake_color_print(text, color, style, prefix, end="\n", file=sys.stdout):
        chamadas.append((text, color, style, prefix))

    real_cp = cl.color_print
    try:
        cl.color_print = fake_color_print
        cl.log_print("x", level="NAO_EXISTE", system="S")
        assert chamadas[0][1] == "bright_white"
    finally:
        cl.color_print = real_cp


def test_colorama_nao_instalado_nao_quebra(monkeypatch, tmp_path):
    """
    Recarrega o módulo simulando ImportError no colorama.
    Garante que o import protegido por try/except não quebre.
    """
    # Cria um simulador de import que falha apenas para 'colorama'
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "colorama":
            raise ImportError("colorama não disponível")
        re


