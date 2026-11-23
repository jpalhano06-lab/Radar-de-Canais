"""O vídeo da fábrica cortado no meio (o disco encheu no render, 2026-11-21) não é "pronto para postar"."""
from radar import servidor


def _caixa(tipo: bytes, corpo: bytes) -> bytes:
    return (8 + len(corpo)).to_bytes(4, "big") + tipo + corpo


INTEIRO = _caixa(b"ftyp", b"isom" * 4) + _caixa(b"mdat", b"\0" * 500) + _caixa(b"moov", b"\1" * 40)


def test_mp4_inteiro_conta(tmp_path):
    (tmp_path / "final.mp4").write_bytes(INTEIRO)
    assert servidor._video_final(tmp_path) == tmp_path / "final.mp4"


def test_mp4_cortado_no_meio_nao_conta(tmp_path):
    (tmp_path / "final.mp4").write_bytes(INTEIRO[:300])
    assert servidor._video_final(tmp_path) is None


def test_mp4_sem_moov_nao_conta(tmp_path):
    (tmp_path / "final.mp4").write_bytes(_caixa(b"ftyp", b"isom" * 4) + _caixa(b"mdat", b"\0" * 500))
    assert servidor._video_final(tmp_path) is None


def test_mdat_de_64_bits(tmp_path):
    corpo = b"\0" * 100
    mdat = (1).to_bytes(4, "big") + b"mdat" + (16 + len(corpo)).to_bytes(8, "big") + corpo
    (tmp_path / "final.mp4").write_bytes(_caixa(b"ftyp", b"isom") + mdat + _caixa(b"moov", b"\1" * 8))
    assert servidor._video_final(tmp_path) == tmp_path / "final.mp4"
