"""Para onde as procuras do app olham (sem rede)."""
from radar import mercado


def test_eua_em_duas_de_cada_tres_buscas():
    paises = [mercado.regiao(n) for n in range(9)]
    assert paises.count("US") == 6 and set(paises) <= set(mercado.PAISES)


def test_nicho_que_paga_pouco_e_historias_narradas_ficam_de_fora():
    assert mercado.irrelevante("Games")
    assert mercado.irrelevante("Animais", "Histórias de Terror")
    assert mercado.irrelevante("Outro", "Contos Animados")


def test_historia_e_historias_reais_ficam():
    assert not mercado.irrelevante("História", "História Militar")
    assert not mercado.irrelevante("Religião", "Histórias da Bíblia")
    assert not mercado.irrelevante("Crimes Reais", "Histórias de Crimes Reais")
    assert not mercado.irrelevante("Carros", "Carros de Luxo")
