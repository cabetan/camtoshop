import hashlib
import hmac
import json

from camtoshop.adaptadores.whatsapp import firma_valida, mensajes_del_webhook


def cuerpo(*mensajes):
    return {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "573001234567", "profile": {"name": "Ana"}}],
                                              "messages": list(mensajes)}}]}]}


def test_lee_foto_texto_audio_y_boton():
    datos = cuerpo(
        {"from": "573001234567", "id": "w1", "type": "image", "image": {"id": "m1", "caption": "Vela 85 mil"}},
        {"from": "573001234567", "id": "w2", "type": "text", "text": {"body": "hola"}},
        {"from": "573001234567", "id": "w3", "type": "audio", "audio": {"id": "a1"}},
        {"from": "573001234567", "id": "w4", "type": "interactive",
         "interactive": {"type": "button_reply", "button_reply": {"id": "publicar|p|v", "title": "Publicar"}}},
    )
    salida = mensajes_del_webhook(datos)
    assert [(m.tipo, m.texto, m.media, m.boton) for _, _, _, m in salida] == [
        ("imagen", "Vela 85 mil", "m1", ""), ("texto", "hola", "", ""), ("audio", "", "a1", ""),
        ("boton", "", "", "publicar|p|v")]
    assert salida[0][:3] == ("573001234567", "w1", "Ana")


def test_estados_de_entrega_no_son_mensajes():
    assert mensajes_del_webhook({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}) == []


def test_firma():
    crudo = json.dumps(cuerpo()).encode()
    firma = "sha256=" + hmac.new(b"secreto", crudo, hashlib.sha256).hexdigest()
    assert firma_valida(crudo, firma, "secreto")
    assert not firma_valida(crudo, firma, "otro") and not firma_valida(crudo, "", "secreto")
