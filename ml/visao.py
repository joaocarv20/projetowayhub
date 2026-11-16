"""
Arquivo: ml/visao.py
Função: visão computacional (OpenCV) — mede o produto por fotos tiradas DE CIMA, com o produto
        em cima de uma folha A4 (a folha é a régua: 21 x 29,7 cm). Foto 1: comprimento x largura.
        Foto 2 (opcional): o produto deitado de lado, que mostra a altura. A descrição define a
        densidade (e a altura típica, se não houver foto 2), que vira o peso estimado.
        Teste rápido:  python3 -m ml.visao
"""
import unicodedata

import cv2
import numpy as np

A4_MM = (210, 297)
PX_POR_MM = 4               # resolução da folha "endireitada" (840 x 1188 px)

# (palavras na descrição, nome, densidade g/cm³, altura típica em cm — None = igual ao menor lado da foto)
# ponytail: tabela por palavra-chave; troque por um classificador se as descrições ficarem variadas demais
PERFIS = [
    (("capinha", "pelicula"), "capinha/película", 0.25, 1.5),
    (("livro", "caderno", "apostila", "revista"), "livro/caderno", 0.7, 3.0),
    (("documento", "envelope", "papel", "carta"), "documento/envelope", 0.4, 1.0),
    (("roupa", "camiseta", "camisa", "calca", "tecido", "toalha"), "roupa/tecido", 0.25, 5.0),
    (("celular", "smartphone", "tablet", "notebook", "eletronico"), "eletrônico", 0.5, None),
    (("garrafa", "bebida", "liquido", "oleo", "perfume"), "líquido", 0.9, None),
    (("ferramenta", "metal", "peca", "parafuso"), "metal/ferramenta", 1.5, None),
]
PERFIL_PADRAO = ("caixa/genérico", 0.2, None)


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", (texto or "").lower()).encode("ascii", "ignore").decode()


def perfil_da_descricao(descricao):
    texto = _sem_acento(descricao)
    for palavras, nome, densidade, altura in PERFIS:
        if any(p in texto for p in palavras):
            return nome, densidade, altura
    return PERFIL_PADRAO


def _ordenar_cantos(pts):
    """Devolve os 4 cantos na ordem: sup. esq., sup. dir., inf. dir., inf. esq."""
    soma, dif = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.float32([pts[soma.argmin()], pts[dif.argmin()], pts[soma.argmax()], pts[dif.argmax()]])


def _endireitar_folha(img):
    """Acha a folha A4 (a maior região clara de 4 cantos) e a "fotografa de frente" (corrige a perspectiva)."""
    cinza = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, clara = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(clara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contornos:
        folha = max(contornos, key=cv2.contourArea)
        cantos = cv2.approxPolyDP(folha, 0.02 * cv2.arcLength(folha, True), True)
        if len(cantos) == 4 and cv2.contourArea(folha) > 0.15 * img.shape[0] * img.shape[1]:
            cantos = _ordenar_cantos(cantos.reshape(4, 2).astype(np.float32))
            largura = np.linalg.norm(cantos[0] - cantos[1])
            altura = np.linalg.norm(cantos[0] - cantos[3])
            w, h = (A4_MM[1], A4_MM[0]) if largura > altura else A4_MM     # folha deitada ou em pé
            w, h = w * PX_POR_MM, h * PX_POR_MM
            destino = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
            return cv2.warpPerspective(img, cv2.getPerspectiveTransform(cantos, destino), (w, h))
    raise ValueError("Não encontrei a folha A4. Coloque o produto inteiro sobre uma folha A4 branca, "
                     "em uma mesa escura, e fotografe de cima mostrando a folha toda.")


def _medir_lados(imagem_bytes):
    """Mede os 2 lados do produto visto de cima. Devolve (maior, menor, imagem anotada RGB)."""
    img = cv2.imdecode(np.frombuffer(imagem_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Não consegui abrir a imagem.")
    escala = 1600 / max(img.shape[:2])
    if escala < 1:
        img = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)

    folha = _endireitar_folha(img)
    m = int(0.03 * min(folha.shape[:2]))              # ignora a bordinha da folha
    miolo = folha[m:-m, m:-m]
    cinza = cv2.GaussianBlur(cv2.cvtColor(miolo, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    # ponytail: produto = o que é mais escuro que a folha; produto branco não aparece (use folha colorida/escura)
    _, objeto = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    objeto = cv2.morphologyEx(objeto, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contornos, _ = cv2.findContours(objeto, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos or cv2.contourArea(max(contornos, key=cv2.contourArea)) < 0.003 * objeto.size:
        raise ValueError("Achei a folha, mas não o produto. Ele precisa contrastar com a folha branca.")

    retangulo = cv2.minAreaRect(max(contornos, key=cv2.contourArea))
    lado_a, lado_b = (round(px / (PX_POR_MM * 10), 1) for px in retangulo[1])
    maior, menor = max(lado_a, lado_b), min(lado_a, lado_b)
    caixa = cv2.boxPoints(retangulo).astype(np.int32) + m
    cv2.drawContours(folha, [caixa], 0, (0, 200, 0), 4)
    cv2.putText(folha, f"{maior} x {menor} cm", tuple(caixa.min(axis=0)), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (0, 0, 255), 3)
    return maior, menor, cv2.cvtColor(folha, cv2.COLOR_BGR2RGB)


def _altura_da_foto_lateral(comprimento, largura, a, b):
    """Na foto do produto deitado de lado aparecem um lado já conhecido (comprimento ou largura) e a altura.
    O lado mais parecido com um dos conhecidos é o repetido; o outro é a altura."""
    erro = lambda lado: min(abs(lado - comprimento), abs(lado - largura))
    return b if erro(a) <= erro(b) else a


def medir_produto(foto_cima, descricao="", foto_lado=None):
    """foto_cima: produto sobre a A4 visto de cima. foto_lado (opcional): o mesmo produto DEITADO DE LADO
    sobre a A4, de novo fotografado de cima — mede a altura. Sem ela, a altura vem da descrição."""
    comprimento, largura, img_cima = _medir_lados(foto_cima)
    imagens = [img_cima]
    nome, densidade, altura = perfil_da_descricao(descricao)
    if foto_lado:
        a, b, img_lado = _medir_lados(foto_lado)
        altura = _altura_da_foto_lateral(comprimento, largura, a, b)
        imagens.append(img_lado)
    altura_medida = bool(foto_lado)
    altura = altura or largura
    volume = comprimento * largura * altura
    peso = max(round(volume * densidade / 1000, 2), 0.01)
    return {"comprimento_cm": comprimento, "largura_cm": largura, "altura_cm": altura,
            "altura_medida": altura_medida, "volume_cm3": round(volume), "peso_kg": peso,
            "perfil": nome, "densidade": densidade, "imagens": imagens}


if __name__ == "__main__":
    def foto_sintetica(lado_mm_a, lado_mm_b, angulo):
        """Folha A4 torta (perspectiva) numa mesa escura, com um retângulo escuro de a x b mm girado."""
        folha = np.full((1188, 840, 3), 245, np.uint8)
        produto = cv2.boxPoints(((420, 600), (lado_mm_a * PX_POR_MM, lado_mm_b * PX_POR_MM), angulo))
        cv2.fillPoly(folha, [produto.astype(np.int32)], (60, 40, 120))
        mesa = np.full((1500, 1300, 3), 50, np.uint8)
        cantos = np.float32([[180, 150], [1050, 200], [1120, 1380], [120, 1300]])
        H = cv2.getPerspectiveTransform(np.float32([[0, 0], [840, 0], [840, 1188], [0, 1188]]), cantos)
        mesa = cv2.warpPerspective(folha, H, (1300, 1500), dst=mesa, borderMode=cv2.BORDER_TRANSPARENT)
        return cv2.imencode(".png", mesa)[1].tobytes()

    # livro de 16 x 8 x 4 cm: de cima mostra 16 x 8; deitado de lado mostra 16 x 4
    r = medir_produto(foto_sintetica(160, 80, 20), "Livro de receitas")
    print({k: v for k, v in r.items() if k != "imagens"})
    assert abs(r["comprimento_cm"] - 16) <= 0.4 and abs(r["largura_cm"] - 8) <= 0.4, r
    assert r["perfil"] == "livro/caderno" and r["altura_cm"] == 3.0 and not r["altura_medida"]
    r = medir_produto(foto_sintetica(160, 80, 20), "Livro de receitas", foto_sintetica(40, 160, -10))
    print({k: v for k, v in r.items() if k != "imagens"})
    assert abs(r["altura_cm"] - 4) <= 0.4 and r["altura_medida"] and len(r["imagens"]) == 2, r
    assert _altura_da_foto_lateral(16, 8, 8, 12) == 12      # deitado mostrando a largura: altura 12
    assert perfil_da_descricao("20 Capinhas de celular")[0] == "capinha/película"
    try:
        medir_produto(cv2.imencode(".png", np.full((500, 500, 3), 50, np.uint8))[1].tobytes())
        raise AssertionError("deveria reclamar que não achou a folha")
    except ValueError:
        pass
    print("ok")
