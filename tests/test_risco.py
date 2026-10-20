"""O risco de desmonetização pelos títulos (sem rede)."""
from radar import risco


def test_compilacao_e_reacao_sao_reaproveitadas():
    titulos = ["Best Fails Compilation 2026", "Funny Animals Compilation #4", "Top Clips of the Week", "Nature video"]
    assert "reaproveitado" in risco.avaliar(titulos)


def test_infantil():
    assert "infantil" in risco.avaliar(["Learn Colors for Kids", "Nursery Rhymes for Toddlers", "Baby Shark Dance"])


def test_feito_em_serie():
    titulos = [f"Top {n} Facts About {x} That Will Shock You" for n, x in
               [(10, "Sharks"), (7, "Cats"), (12, "Dogs"), (9, "Owls"), (5, "Bats"), (8, "Frogs")]]
    assert "em_serie" in risco.avaliar(titulos)


def test_documentario_normal_nao_tem_risco():
    titulos = ["The Rise and Fall of Blockbuster", "Why Toys R Us Really Failed", "How Costco Makes Money",
               "The Collapse of Sears Explained", "Inside the World's Biggest Shipping Company", "What Happened to Kodak"]
    assert risco.avaliar(titulos) == []
