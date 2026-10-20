"""python -m radar servidor | garimpar [--unidades N] | canal UC...|@handle | cota"""
import argparse
import json


def main():
    p = argparse.ArgumentParser(prog="radar")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("servidor", help="liga o site e a API da extensão")
    s.add_argument("--porta", type=int)
    s.add_argument("--publico", action="store_true", help="aceita conexões de outros computadores (0.0.0.0)")
    g = sub.add_parser("garimpar", help="procura canais novos agora")
    g.add_argument("--unidades", type=int, help="teto de cota do YouTube para este garimpo")
    c = sub.add_parser("canal", help="mede um canal e mostra os números")
    c.add_argument("ref")
    sub.add_parser("cota", help="quanto da cota do YouTube já foi usado hoje")
    a = p.parse_args()

    if a.comando == "servidor":
        import uvicorn
        from .config import PORTA
        if a.publico:
            import os
            os.environ["RADAR_ABERTO"] = "0"     # aberto para a rede: a senha volta
        uvicorn.run("radar.servidor:app", host="0.0.0.0" if a.publico else "127.0.0.1", port=a.porta or PORTA)
    elif a.comando == "garimpar":
        from . import garimpo
        print(json.dumps(garimpo.rodar(unidades=a.unidades), ensure_ascii=False))
    elif a.comando == "canal":
        from . import medir, youtube
        ref = a.ref
        if ref.startswith("@"):
            achado = youtube.canal_por_handle(ref)
            ref = achado["id"] if achado else ref
        dados = medir.canal_completo(ref)
        if dados:
            dados["videos"] = dados["videos"][:10]
        print(json.dumps(dados, ensure_ascii=False, indent=1))
    elif a.comando == "cota":
        from . import youtube
        print(json.dumps(youtube.cota_hoje()))


if __name__ == "__main__":
    main()
