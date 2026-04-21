import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv
from pyairtable import Api

PROMPT = '''Eres un evaluador experto de Recursos Humanos. Tu tarea es analizar la siguiente transcripción de una entrevista para el rol de "AI Automation Builder" y extraer datos específicos para registrar en nuestra base de datos.

Revisa la transcripción y devuelve un objeto JSON estructurado que pueda ser mapeado a Airtable con los siguientes campos:
{
 "Nombre del candidato": "Extrae el nombre completo del candidato",
 "Rol": "AI Automation Builder",
 "Fecha": "Genera la fecha actual en formato YYYY-MM-DD",
 "Nivel de inglés hablado": "Evalúa del 1 al 5",
 "Fit técnico": "Evalúa del 1 al 5",
 "Fit cultural": "Evalúa del 1 al 5",
 "Fortalezas clave": "Resume brevemente",
 "Preocupaciones clave": "Resume brevemente",
 "Recomendación": "Responde estrictamente: Avanzar, Pausar o Rechazar"
}

Aquí está la transcripción a evaluar:
[00:00:00] Aaron Barrios: Hola Juan, bienvenido a la entrevista para el rol de AI Automation Builder. ¿Cómo estás?
[00:00:05] Juan Perez: Hola Aaron, todo muy bien, gracias por la oportunidad.
[00:00:15] Juan Perez: Llevo 3 años trabajando como especialista en automatizaciones. Uso Make.com casi a diario para integrar diferentes CRMs con bases de datos como Airtable y Google Sheets. Recientemente construí un sistema que toma leads de Facebook, los enriquece con ChatGPT y los clasifica en Airtable.
[00:00:40] Juan Perez: Tengo un nivel intermedio-alto, diría que un B2. Puedo leer y escribir documentación sin problemas, y mantener conversaciones técnicas, aunque mi acento es un poco marcado.
[00:01:00] Juan Perez: Siempre uso variables de entorno o gestores de secretos dentro de la plataforma que esté usando, nunca dejo las keys quemadas en el código o en texto plano.
[00:01:20] Juan Perez: Me encanta la autonomía. Prefiero que me den el problema y yo buscar la solución. A veces el ritmo rápido hace que la documentación quede rezagada, pero intento mantener un balance.'''


def extract_json(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    if obj:
        return json.loads(obj.group(0))
    raise ValueError("No JSON object found in response")


def main() -> None:
    try:
        print("[1/5] Cargando variables de entorno...")
        load_dotenv()
        anthropic_key = os.environ["ANTHROPIC_API_KEY"]
        airtable_token = os.environ["AIRTABLE_TOKEN"]
        airtable_base_id = os.environ["AIRTABLE_BASE_ID"]
        airtable_table_name = os.environ["AIRTABLE_TABLE_NAME"]
    except KeyError as e:
        print(f"Error: falta la variable de entorno {e}")
        return
    except Exception as e:
        print(f"Error cargando .env: {e}")
        return

    try:
        print("[2/5] Llamando a la API de Anthropic (claude-opus-4-5)...")
        client = Anthropic(api_key=anthropic_key)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": PROMPT}],
        )
        raw_text = message.content[0].text
    except Exception as e:
        print(f"Error llamando a Anthropic: {e}")
        return

    try:
        print("[3/5] Extrayendo JSON de la respuesta...")
        data = extract_json(raw_text)
    except Exception as e:
        print(f"Error extrayendo JSON: {e}\nRespuesta cruda:\n{raw_text}")
        return

    try:
        print("[4/5] Conectando con Airtable...")
        api = Api(airtable_token)
        table = api.table(airtable_base_id, airtable_table_name)
    except Exception as e:
        print(f"Error conectando con Airtable: {e}")
        return

    try:
        print("[5/5] Creando registro en Airtable...")
        clean = {k: (v.strip().strip('"').strip("'") if isinstance(v, str) else v)
                 for k, v in data.items()}
        current = dict(clean)
        record = None
        for _ in range(len(clean) + 1):
            try:
                record = table.create(current, typecast=True)
                break
            except Exception as err:
                msg = str(err)
                bad = next((f for f in list(current.keys()) if f in msg), None)
                if bad is None:
                    bad = next(
                        (f for f, v in current.items()
                         if isinstance(v, str) and v and v in msg),
                        None,
                    )
                if not bad or not current:
                    raise
                print(f"  Campo problemático '{bad}' — lo omito y reintento...")
                current.pop(bad)
        if record is None:
            raise RuntimeError("No se pudo crear el registro tras reintentos")
        print(f"Registro creado con id: {record.get('id')}")
        if len(current) < len(clean):
            omitted = set(clean) - set(current)
            print(f"Campos omitidos por incompatibilidad con Airtable: {sorted(omitted)}")
    except Exception as e:
        print(f"Error creando registro en Airtable: {e}")
        return


if __name__ == "__main__":
    main()
