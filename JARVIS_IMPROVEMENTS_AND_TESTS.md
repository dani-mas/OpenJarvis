# Jarvis - Mejoras completas y plan de tests

## Vision

Jarvis debe ser una app local de voz, minimalista, rapida y fiable:

- Siempre escucha en segundo plano.
- Solo despierta con frases tipo "Hola Jarvis".
- Si esta escondido, vuelve con "quiero verte", "muestra el panel" o frases similares.
- Si esta hablando y el usuario le corta, se calla y prioriza la nueva orden.
- Puede ejecutar acciones locales: abrir apps, perfiles de Chrome, proyectos, webs, carpetas y comandos.
- Puede inspeccionar codigo local:
  - todos los repos bajo `C:\Users\dani2\github`.
  - rama actual.
  - upstream.
  - cambios modificados, staged y untracked.
  - commits pendientes de push/pull.
  - ultimo commit.
- Puede mostrar un panel visual de repos en la UI con frases como:
  - "estado de repos".
  - "que cambios hay en github".
  - "panel de codigo".
- Puede lanzar Codex con permisos de escritura para tareas de codigo cuando la orden sea explicita:
  - "mejora jarvis ...".
  - "modifica codigo ...".
  - "modo codigo implementa ...".
  - Por defecto las consultas de codigo siguen en solo lectura.
- Usa Codex CLI como motor de razonamiento, sin depender de `OPENAI_API_KEY` en la app.
- No deja procesos duplicados ni ventanas de terminal colgadas.
- La interfaz es limpia: fondo negro, globo de particulas blancas, texto retro y respuesta por voz.
- La interfaz muestra flujos de trabajo como orbitas flotantes:
  - Ditelba.
  - Codu.
  - HGR.
- Cada flujo tiene espacio visual para cuentas, repositorios y herramientas conectadas.

## Estado actual implementado

- App local Tkinter fullscreen.
- Wake listener local con Whisper open-source.
- STT local con `faster-whisper`.
- STT separado por contexto:
  - Wake usa `OPENJARVIS_WAKE_WHISPER_MODEL`, por defecto `small`.
  - Wake exige al menos `OPENJARVIS_WAKE_STT_MIN_VOICE_BLOCKS=4` bloques de voz para no transcribir ruido corto.
  - Comandos usan `OPENJARVIS_COMMAND_WHISPER_MODEL`, por defecto `auto`.
  - En `auto`, Jarvis usa `base` si esta cacheado y vuelve a `small` si no lo esta.
  - Si el modelo de comandos falla al cargar, vuelve a `small` para no dejar Jarvis mudo.
  - Para priorizar precision sobre latencia se puede usar temporalmente `OPENJARVIS_COMMAND_WHISPER_MODEL=large-v3-turbo`.
  - La UI no descarga modelos en caliente: `local_files_only=True` por defecto para evitar bloqueos despues de "Hola Jarvis".
  - Las descargas de modelos deben hacerse de forma explicita fuera de una conversacion, o con `OPENJARVIS_WHISPER_ALLOW_DOWNLOAD=1`.
  - `base` queda descargado y validado localmente para comandos cortos rapidos.
  - `large-v3-turbo` queda disponible como opcion local de mas precision, pero no es el valor por defecto porque aumenta la latencia.
  - Si Whisper local no oye nada, ya no se usa Windows Speech Recognition porque generaba basura como "El" o "Pero el". En escritorio, Jarvis usa Whisper solamente.
  - Las alucinaciones repetitivas de silencio/ruido ("un video...", "lo que es...", secuencias numericas) se filtran antes de llegar al wake/router.
  - Las transcripciones que no son wake/show no se registran como `wake_heard`; se ignoran para no confundir los diagnosticos.
  - El saludo inicial ya no abre el micro mientras Jarvis esta hablando para evitar que transcriba su propio "que deseas".
  - Jarvis ya no vuelve a abrir micro mientras sigue hablando una respuesta; espera a terminar.
  - El corte/interrupcion por voz mientras Jarvis habla queda desactivado por defecto porque los logs mostraron eco TTS convertido en orden falsa.
  - `OPENJARVIS_EARLY_LISTEN_MS` y `OPENJARVIS_RESPONSE_EARLY_LISTEN_MS` permiten reactivar escucha temprana de forma explicita.
  - Transcripciones basura como "El", "Pero el" o frases cortadas con "..." se ignoran antes de llegar a Codex.
  - Las respuestas de voz ya no fuerzan una frase ultracorta. Chat y recomendaciones pueden responder con 2-4 frases o bullets utiles.
  - Jarvis debe explicar que falta cuando no puede leer un dato privado como correo/calendario, en vez de responder solo "Hecho".
  - Conversacion normal no usa respuestas fijas locales; pasa por Codex para que Jarvis piense realmente.
  - Chat ya no manda contexto de repo ni permisos a Codex. Solo el modo codigo resuelve workspace y lee repos.
  - La ventana fija de comando es 5.8 s si se activa el modo fijo.
  - El modo dinamico de comandos usa margen de silencio rapido: `OPENJARVIS_COMMAND_STT_SILENCE_SECONDS=1.15`.
  - El modo dinamico limita cada frase con `OPENJARVIS_COMMAND_STT_MAX_RECORDING_SECONDS=5.6`.
  - Los comandos usan STT dinamico por defecto: graba hasta detectar silencio, en vez de esperar siempre toda la ventana fija.
  - `OPENJARVIS_COMMAND_STT_MODE=fixed` permite volver al modo de ventana fija para depuracion.
  - Whisper usa GPU automaticamente cuando `ctranslate2` detecta CUDA: por defecto `cuda/float16`; si no hay CUDA vuelve a `cpu/int8`.
  - `OPENJARVIS_WHISPER_DEVICE=cpu` fuerza CPU y `OPENJARVIS_WHISPER_DEVICE=cuda` fuerza GPU.
  - `OPENJARVIS_WHISPER_COMPUTE_TYPE`, `OPENJARVIS_CUDA_WHISPER_COMPUTE_TYPE` y `OPENJARVIS_CPU_WHISPER_COMPUTE_TYPE` permiten ajustar precision/rendimiento.
  - `jarvis voice-status` y `jarvis voice-doctor` muestran `STT runtime`, por ejemplo `cuda/float16`.
  - `jarvis voice-doctor` muestra si hay GPU pero faltan DLLs CUDA/cuBLAS; en ese caso Jarvis usa `cpu/int8`.
  - La escucha dinamica corta por silencio, pero tambien limita la grabacion tras empezar a hablar con `OPENJARVIS_STT_MAX_RECORDING_SECONDS` para evitar esperas de 12 s por ruido de fondo.
  - Frases como "mejorate a ti mismo" entran en modo codigo con permiso de escritura sobre el repo `jarvis`.
  - La UI muestra `JARVIS PIPE:// actividad` con progreso operativo: repo elegido, permisos, lectura git, lanzamiento de Codex y resultado recibido.
  - Codex recibe tanto la transcripcion original como la orden interpretada, para no perder intencion en frases como "mejorate a ti mismo".
  - "hazlo", "dale" y "adelante" reutilizan la ultima orden accionable si existe.
- Whisper recibe prompt y hotwords de vocabulario Jarvis/Codu para comandos; el wake usa solo hotwords para evitar alucinaciones del prompt cuando hay silencio.
  - La app espera a terminar el saludo antes de abrir el micro, evitando que Jarvis se transcriba a si mismo.
- Los logs registran `app_listen_started`, `app_stt_started`, `app_stt_finished`, `app_stt_empty` y `app_stt_failed`.
- Correccion centralizada de transcript en `local_stt.py`:
  - "hora jarvis" -> "Hola Jarvis".
  - "cobo/code/codi/codu taim" -> "codu time".
  - "modo codo/cobo/godo" -> "modo codu".
- Umbral de micro mas sensible por defecto: `OPENJARVIS_STT_THRESHOLD=0.0035`.
- Micro configurable:
  - `OPENJARVIS_STT_DEVICE=3`
  - `OPENJARVIS_STT_DEVICE="Microfono USB"`
  - `OPENJARVIS_MICROPHONE_DEVICE` funciona como alias.
- TTS local con Windows SAPI.
- Motor por defecto: Codex CLI.
- Modelo Codex por defecto: `gpt-5.5`.
- Canal interno de control:
  - `show`: mostrar app.
  - `hide`: esconder app.
  - `wake`: mostrar app y volver a preguntar.
  - `close`: cerrar app.
- Estado interno de la app:
  - `visible`: el wake deja libre el micro para la app.
  - `hidden`: el wake escucha para poder volver con "Hola Jarvis" o "quiero verte".
  - `closing/closed`: diagnostico de cierre.
- Comandos de voz:
  - "Hola Jarvis": despierta.
  - Tambien despiertan malas transcripciones reales como "hora jarvis" y "por allervis".
  - Ya no despiertan falsos positivos como "hola" u "ola ola ola ola".
  - "quiero verte": muestra la interfaz.
  - "escondete": esconde la interfaz.
  - `Esc`: esconde la interfaz, no cierra Jarvis.
  - "adios Jarvis": cierra la app.
  - "codu time": abre Monitoring, Notion y `C:\Users\dani2\github\C4-KNX` en Cursor.
  - "modo codu" o "codu tiempo": hacen lo mismo sin depender de la palabra inglesa "time".
  - Tambien acepta malas transcripciones reales como "codigo time codigo", "cobo time", "modo godo", "mono codu" y "quiero que pongas el modo cordelo".
  - Cuando detecta Codu, responde corto, lanza Chrome/Cursor/Docker y cierra la app. El wake listener queda vivo.
  - Tambien abre Docker Desktop y ejecuta `docker compose -f docker-compose.dev.yml up --build -d` en `C:\Users\dani2\github\C4-KNX`.
  - El log del arranque Docker queda en `logs\codu-docker-dev.log`.
  - El log del arranque Cursor queda en `logs\codu-cursor.log`.
  - Coloca Chrome en la mitad izquierda del monitor y Cursor en la mitad derecha.
  - El layout selecciona Chrome por titulos de Codu/Grafana/Notion para no mover una ventana equivocada como WhatsApp.
  - El log de layout guarda posicion pedida y posicion real (`requested`/`actual`).
  - El log del layout de ventanas queda en `logs\codu-window-layout.log`.
- Log de voz:
  - `logs\jarvis-voice-events.jsonl` guarda wake/app, texto reconocido y ruta tomada.
  - Rota automaticamente a `.1` al superar `OPENJARVIS_VOICE_LOG_MAX_BYTES` o 1 MB por defecto.
  - Redacta automaticamente claves/tokens/contraseñas antes de escribir a disco.
  - `OPENJARVIS_VOICE_LOG_REDACTION=0` permite desactivar la redaccion solo para depuracion puntual.
  - Limita campos de texto grandes con `OPENJARVIS_VOICE_LOG_MAX_FIELD_CHARS` para que errores enormes no rompan los diagnosticos.
- Comando de test por texto:
  - `jarvis voice-send "codu time"` inyecta una frase como si viniera del micro.
- Comando de diagnostico:
  - `jarvis voice-status` muestra wake/app, duplicados, modelos STT, micro seleccionado, ultimo control y ultimo evento de voz.
  - Por voz, "lee logs", "mira los logs", "estado de voz" o "estado del microfono" muestran diagnostico y eventos recientes en la interfaz.
- Comando de arranque sin terminal visible:
  - `jarvis voice-start` inicia el wake listener en segundo plano.
  - Usa Whisper, app desktop, Codex y `gpt-5.5` por defecto.
  - Sustituye wake listeners existentes para evitar duplicados.
- Comando de reinicio limpio:
  - `jarvis voice-restart` para wake/app, marca estado desktop como `closed` y arranca un unico wake listener oculto.
- Comando de logs:
  - `jarvis voice-logs` muestra eventos recientes en formato humano.
  - `jarvis voice-logs --json` muestra los eventos JSON sin procesar.
- Comando de microfonos:
  - `jarvis voice-devices` lista microfonos de entrada, indice, canales y sample rate.
  - Marca un dispositivo `recommended` para acelerar la seleccion del micro.
  - Sirve para fijar `OPENJARVIS_STT_DEVICE` cuando Windows elige mal el micro.
- Comando doctor:
  - `jarvis voice-doctor` agrupa Codex CLI, modelos Whisper, micro seleccionado, startup, acciones, procesos y logs.
  - Por voz, "diagnostico completo jarvis" muestra este informe en la interfaz.
- Arranque con Windows:
  - `jarvis voice-startup install` crea un launcher oculto en Startup.
  - `jarvis voice-startup status` comprueba si esta instalado.
  - `jarvis voice-startup uninstall` lo elimina.
- Comando de diagnostico de codigo:
  - `jarvis code-status` muestra el panel de repos local.
  - `jarvis code-status --root C:\Users\dani2\github\C4-KNX` limita el escaneo a una carpeta.
- Comando de parada controlada:
  - `jarvis voice-stop --dry-run` muestra que procesos de voz pararia.
  - `jarvis voice-stop` para wake/app sin tocar procesos ajenos.
- Acciones locales configurables:
  - `jarvis_actions.json` en el workspace.
  - `OPENJARVIS_ACTIONS_FILE` permite apuntar a otro archivo.
  - Cada accion acepta `triggers`, `commands` como listas de argumentos y `open` para URLs/rutas.
  - Ejemplo en `examples\voice_modes\jarvis_actions.example.json`.
  - `jarvis voice-actions` lista acciones y triggers configurados.
  - Por voz, "que acciones tienes" muestra ese listado.
  - Apertura generica del ordenador:
  - `abre gmail`, `abre correo`, `abre mis correos` abren Gmail en Chrome.
  - `abre calendario`, `abre agenda`, `abre Google Calendar` abren Google Calendar en Chrome.
  - Las frases tipo "mira mis correos", "hay algo importante en mi correo", "mira mi calendario" pasan al planificador IA.
  - El planificador IA tiene acciones internas `gmail_summary` y `calendar_summary`.
  - Si los conectores oficiales `gmail`/`gcalendar` estan configurados, Jarvis puede resumir correos recientes y agenda de hoy.
  - Si no hay conector/API de Gmail o Calendar, Jarvis no inventa contenido: propone abrir la web o configurar acceso con `jarvis connect gmail` / `jarvis connect gcalendar`.
  - `abre spotify`, `pon spotify` y `pon musica` usan el protocolo `spotify:`.
  - `ponme una alarma a las 10 y 25`, `configurame una alarma para las 10:25`, `consigurame una alarma para las 10 y 25` crean una tarea real de Windows.
  - `recuerdame llamar a Dani a las 18:30` o `avisame en 5 minutos` crean recordatorios reales.
  - Al dispararse, Jarvis habla el recordatorio y muestra una ventana local `JARVIS:// RECORDATORIO`.
  - Los recordatorios se auditan en `logs\jarvis-reminders.jsonl` y tambien en `logs\jarvis-voice-events.jsonl`.
  - Si no detecta una hora clara, abre Windows Clock con `ms-clock:` en vez de inventar una hora.
  - `abre descargas`, `abre documentos`, `abre escritorio`, `abre github`, `abre c4 knx` abren carpetas conocidas.
  - Si no hay comando fijo, `abre <app>` busca accesos directos instalados en el menu Inicio de Windows.
  - El indice de apps instaladas se cachea durante el proceso para reducir latencia.
  - `jarvis voice-context` muestra contexto local: ventanas visibles, apps instaladas, acciones, repos y Codex.
  - Por voz, "contexto del ordenador", "que puedes abrir" o "apps instaladas" muestran ese contexto.
- Planificador IA de acciones:
  - Las ordenes no-code que no sean accion local directa pasan por Codex como cerebro de planificacion.
  - Codex devuelve JSON estructurado con acciones permitidas: `open`, `reply`, `codex_task`, `show_context`, `voice_status`, `voice_doctor`, `list_actions`, `list_microphones`.
  - `codex_task` permite que la IA delegue una tarea completa a Codex en modo `chat`, `code`, `research`, `digest` o `monitor`.
  - `configured_action` permite que la IA ejecute por nombre una accion de `jarvis_actions.json`, aunque la frase hablada no coincida exactamente con un trigger.
  - Si dices algo como "quiero que te mejores", "arregla este repo" o "mira mis repos y piensa que hacer", Jarvis puede elegir `codex_task` en modo `code` sin depender de que digas literalmente "modo codigo".
  - Frases de accion con correo/email/Gmail pasan al planificador IA en vez de chat generico, pero el planificador sigue sin poder enviar correos destructivos ni usar credenciales.
  - La UI muestra pasos como `ia: preparando plan`, `ia: pensando accion`, `ia: delegando en codex/code`, repo elegido, permisos y resultado recibido.
  - La fase de planificacion usa timeout propio corto (`OPENJARVIS_AI_PLANNER_TIMEOUT_SECONDS`, por defecto 90 s) aunque la tarea larga de Codex pueda seguir usando mas tiempo.
  - Jarvis ejecuta solo esos tipos seguros; no ejecuta shell arbitrario ni acciones destructivas desde el plan.
  - `OPENJARVIS_AI_ACTION_PLANNER=0` desactiva esta capa si se quiere volver al modo anterior.
  - `jarvis voice-plan "..."` muestra el plan JSON que haria la IA.
  - `jarvis voice-plan "..." --execute` ejecuta el plan seguro desde texto.
- Rendimiento UI configurable:
  - `OPENJARVIS_MAX_PARTICLES=900` limita particulas.
  - `OPENJARVIS_PARTICLE_COUNT=500` fuerza un numero concreto.
  - `OPENJARVIS_UI_FRAME_MS=50` baja FPS para reducir carga.
- Superficie de workflows:
  - Tres orbitas flotantes alrededor del globo: `Ditelba`, `Codu`, `HGR`.
  - Sidebar retro `WORKFLOWS://` con cuenta, repo principal, herramientas y estado.
  - `Codu` aparece conectado con `info@coduworks.com`, `C4-KNX`, Monitoring, Notion, Cursor y Docker.
  - `Ditelba` y `HGR` quedan preparados como pendientes de conectar cuenta/repos.
- Tests automaticos actuales: `tests\voice_modes`.

## Revision de mejores practicas oficiales OpenJarvis

- Agentes:
  - Chat normal sigue el equivalente a modo directo/simple: una consulta corta a Codex, sin contexto de repos ni dashboard de codigo.
  - Codigo y cambios de repos entran en modo `code`, con workspace resuelto, permisos explicitos y comportamiento de orquestador.
  - Acciones locales no-code pasan por el planificador IA solo cuando hay intencion de accion y objetivo local; las conversaciones simples no usan planificador.
- Query flow y telemetria:
  - STT ya registra inicio, fin, silencio, errores, runtime y metricas de grabacion.
  - Codex voz registra ahora `codex_voice_started`, `codex_voice_finished`, `codex_voice_timeout` y `codex_voice_unavailable` con modo, modelo, sandbox, duracion y tamano de respuesta.
  - El planificador IA registra ahora `ai_action_plan_started`, `ai_action_plan_finished`, `ai_action_plan_timeout`, `ai_action_plan_parse_failed` y `ai_action_plan_executed`.
  - Estos eventos permiten saber si la latencia viene de STT, planificador, Codex o accion local.
- Seguridad:
  - El planificador IA devuelve JSON validado y solo acepta acciones permitidas.
  - No hay shell arbitrario desde voz.
  - Las acciones destructivas y credenciales quedan fuera del esquema.
  - Codex en chat usa sandbox `read-only`; solo modo codigo con verbos de cambio usa `workspace-write`.
  - Los logs de voz aplican redaccion defensiva de secretos y limite por campo antes de persistir eventos.
- Configuracion y hardware:
  - Whisper local usa CUDA/float16 cuando las DLLs NVIDIA estan disponibles y vuelve a CPU/int8 si no.
  - `voice-doctor` y `voice-status` muestran runtime STT, modelo, microfono, procesos y logs.
- Roadmap voz:
  - La voz oficial esta marcada como `Research-Stage`; por eso este wrapper conserva controles propios de wake, TTS, UI, procesos y diagnostico.

## Recomendacion STT local para espanol

- Nota de arquitectura OpenJarvis: para respuestas cortas se debe usar el agente mas simple posible; `simple` hace una sola inferencia, mientras `orchestrator` queda para acciones con herramientas. La voz oficial sigue marcada como `Research-Stage`, asi que el wrapper local debe optimizar latencia, wake y TTS por su cuenta.
- Modelo principal recomendado para tu uso actual: `base` con `faster-whisper`.
  - Motivo: los logs muestran que `small` en CPU tarda demasiado en frases cortas; `base` reduce latencia manteniendo buen espanol para comandos como "modo codu", "codu time" y "quiero verte".
  - Uso en Jarvis: comandos cortos y acciones locales.
- Modelo wake recomendado: `small`.
  - Motivo: el wake debe estar siempre escuchando y no debe consumir tantos recursos solo para detectar "Hola Jarvis".
- Modelo equilibrado de fallback: `small`.
  - Motivo: mas fiable que `base` para frases raras, pero mas lento en CPU.
- Modelo de precision: `large-v3-turbo`.
  - Motivo: mejor para dictado largo o transcripciones dificiles, pero no debe ser el default de comandos porque se nota lento en conversacion.
- Alternativa maxima precision: `large-v3`.
  - Motivo: algo mas preciso, pero con mas latencia y memoria.
- Alternativa muy ligera: Vosk `vosk-model-es-0.42`.
  - Motivo: funciona offline y pesa menos, pero no suele entender lenguaje natural y nombres propios tan bien como Whisper.
- Alternativa experimental: NVIDIA Canary 1B.
  - Motivo: buenos resultados en espanol, pero exige integrar NeMo y una pila mas pesada que `faster-whisper`.

## Mejoras prioritarias

### P0 - Fiabilidad basica

- Evitar instancias duplicadas de wake/app.
- Comando `jarvis status`:
  - wake PID.
  - app PID.
  - ultimo comando de control recibido.
  - ultimo texto reconocido.
  - motor STT/TTS activo.
- Comando `jarvis restart-voice`:
  - para wake/app.
  - limpia procesos colgados.
  - reinicia una unica instancia.
- Log rotativo para:
  - wake listener.
  - app desktop.
  - STT.
  - TTS.
  - Codex CLI.
- Deteccion de crash:
  - si la app muere, wake sigue vivo.
  - si wake muere, comando de arranque lo reemplaza limpio.
- No abrir terminal visible nunca en uso normal.

### P0 - Voz y escucha

- Mantener micro activo de forma continua cuando la app esta abierta.
- Separar wake listener y command listener sin pisarse el micro.
- El wake listener debe pausar su propia captura cuando la app esta visible, para no competir por el micro ni disparar saludos repetidos.
- Mejorar reconocimiento de frases cortas:
  - "hola jarvis".
  - "quiero verte".
  - "codu time".
  - "escondete".
  - "callate".
  - "adios jarvis".
- Anadir alias foneticos para errores de Whisper:
  - "codi time", "code time", "con tu time", "codutime".
  - "hola jervis", "hola yamis", "hola ya lo ves".
- Reducir latencia de STT:
  - ventana dinamica de escucha.
  - `base` para comandos y `small` para wake.
  - VAD local open-source.
  - cortar grabacion al detectar fin de frase real.
- Mostrar en UI:
  - texto parcial detectado.
  - texto final reconocido.
  - nivel de micro.
  - estado: wake, escuchando, procesando, hablando.

### P0 - Interrupcion de Jarvis

- Si Jarvis habla y el usuario dice algo, cortar TTS inmediatamente.
- Ignorar eco de la propia voz de Jarvis.
- Si el usuario dice "callate", "para" o "silencio", detener TTS y no responder con otra frase.
- Si el usuario da una nueva orden mientras Jarvis habla, cancelar respuesta anterior y procesar la nueva.
- Evitar carreras:
  - una respuesta vieja no debe empezar a hablar despues de ser cancelada.
  - una orden nueva debe invalidar generaciones anteriores de TTS.

### P1 - Interfaz

- Mantener fullscreen real sin romper Alt+Tab.
- Modo escondido:
  - ocultar ventana.
  - mantener procesos vivos.
  - permitir volver con voz.
- Particulas:
  - menos particulas en PCs lentos.
  - movimiento irregular natural.
  - reaccion al volumen de voz.
  - reaccion distinta al escuchar, procesar y hablar.
- Tema visual:
  - fondo negro.
  - particulas blancas.
  - texto retro discreto.
  - sin topbar ni terminal visible.
- Ajuste automatico de rendimiento:
  - reducir FPS si hay lag.
  - reducir particulas si el render tarda demasiado.
- Modo debug opcional:
  - mostrar FPS.
  - mostrar RMS micro.
  - mostrar ultimo transcript.

### P1 - Acciones locales

- Hacer acciones configurables en un archivo local:
  - `jarvis_actions.json` o `jarvis_actions.toml`.
- Acciones tipo:
  - abrir web.
  - abrir app.
  - abrir carpeta.
  - abrir proyecto en Cursor.
  - ejecutar comando seguro.
  - abrir Chrome con perfil concreto.
- Confirmaciones para acciones peligrosas:
  - borrar archivos.
  - cerrar procesos.
  - mover carpetas.
  - ejecutar comandos admin.
- Acciones sugeridas:
  - "codu time".
  - "abre cursor".
  - "abre monitoring".
  - "abre notion".
  - "abre whatsapp".
  - "captura pantalla".
  - "lee lo que hay en pantalla" si se integra OCR.
  - "resume esta carpeta".
  - "haz commit" solo con confirmacion.

### P1 - Codex

- Mantener Codex CLI como motor principal.
- Medir tiempo de respuesta Codex por orden.
- Modo rapido:
  - modelo spark.
  - respuestas cortas.
  - sin razonamiento largo para ordenes simples.
- Modo profundo:
  - modelo superior.
  - usar solo cuando el usuario diga "piensa bien", "analiza", "trabaja en esto".
- Cancelacion:
  - si el usuario interrumpe, cancelar o ignorar respuesta Codex anterior.
- Contexto:
  - pasar a Codex solo la orden y el modo necesario.
  - no mandar ruido de STT.
- Fallback:
  - si Codex CLI no esta disponible, mostrar mensaje claro en UI.
  - no pedir `OPENAI_API_KEY` si el motor activo es Codex CLI.

### P2 - Memoria y personalizacion

- Guardar preferencias:
  - voz.
  - velocidad TTS.
  - perfil Chrome.
  - rutas de proyectos.
  - frases alias.
  - nivel de particulas.
- Memoria local simple:
  - nombre del usuario.
  - proyectos frecuentes.
  - acciones favoritas.
- Panel de configuracion:
  - selector STT.
  - selector TTS.
  - modelo Codex.
  - rutas y perfiles.
- Exportar/importar configuracion.

### P2 - Arranque con Windows

- Opcion para iniciar wake listener al arrancar Windows.
- Instalar tarea programada o acceso directo en Startup.
- Debe arrancar solo wake listener, no mostrar la app.
- Tras reinicio:
  - Jarvis queda escuchando "Hola Jarvis".
  - no se abre interfaz hasta wake.
- Comando:
  - `jarvis install-startup`
  - `jarvis uninstall-startup`
  - `jarvis startup-status`

### P2 - Observabilidad

- Carpeta `logs/` con:
  - `jarvis-wake.out.log`
  - `jarvis-wake.err.log`
  - `jarvis-app.out.log`
  - `jarvis-app.err.log`
  - `jarvis-actions.log`
- Log estructurado JSONL opcional:
  - timestamp.
  - evento.
  - transcript.
  - accion.
  - latencia.
  - resultado.
- Comando `jarvis logs --tail`.
- Panel debug en la UI.

### P3 - Funciones avanzadas

- Hotword local mas eficiente que Whisper para "Hola Jarvis".
- Wake word dedicado tipo Porcupine/openWakeWord si encaja.
- STT streaming real.
- TTS neural local opcional.
- Control del sistema:
  - volumen.
  - brillo.
  - ventanas.
  - abrir/cerrar apps.
- Vision:
  - screenshot.
  - OCR.
  - describir pantalla.
- Modo agente:
  - ejecutar tareas largas en background.
  - mostrar progreso en UI.
  - permitir cancelar por voz.

## Matriz de tests automaticos

Ejecutar todos los tests de voz:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes
```

Ejecutar con detalle:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes -vv
```

Ejecutar un archivo concreto:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes\test_wake_listener.py -vv
```

Enviar una orden manual por texto a la app viva:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "codu time"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "modo codu"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "codu tiempo"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "quiero que pongas el modo cordelo"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "quiero verte"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-send "escondete"
```

Esto no usa micro. Es util para probar acciones reales cuando no se puede hablar.

Revisar procesos y duplicados:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-status
```

Revisar eventos recientes:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-logs
```

Listar microfonos:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-devices
```

Doctor completo:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-doctor
```

Listar acciones configuradas:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-actions
```

Ver contexto local del ordenador:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-context
```

Probar el planificador IA:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-plan "abre spotify"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-plan "abre spotify" --execute
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-plan "quiero que te mejores para ser mas util"
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-plan "mira mis repos y dime que deberia tocar"
```

Reinicio limpio:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-restart
```

Instalar arranque con Windows:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-startup install
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-startup status
```

Ver que pararia sin cerrar Jarvis:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-stop --dry-run
```

### Unit tests actuales

| Archivo | Que valida |
| --- | --- |
| `test_codex_cli.py` | disponibilidad y ejecucion de Codex CLI |
| `test_configured_actions.py` | carga y ejecucion de `jarvis_actions.json` |
| `test_computer_context.py` | contexto local de ordenador para Jarvis |
| `test_desktop_control.py` | canal `show/hide/wake/close/text` |
| `test_desktop_voice_app.py` | comandos mostrar/esconder/interrumpir y eco TTS |
| `test_local_actions.py` | acciones locales, incluido `codu time` |
| `test_local_stt.py` | STT local, filtros y niveles |
| `test_local_tts.py` | TTS SAPI, rate, voz y comando |
| `test_manual_text_actions.py` | acciones simuladas por texto sin micro |
| `test_voice_actions_cli.py` | CLI `voice-actions` para listar acciones configuradas |
| `test_installed_apps.py` | descubrimiento y apertura de apps instaladas |
| `test_voice_context_cli.py` | CLI `voice-context` |
| `test_voice_action_plan.py` | planificador IA de acciones seguras |
| `test_voice_interface.py` | interfaz y ejecucion de ordenes de voz |
| `test_voice_devices_cli.py` | CLI `voice-devices` para seleccionar micro |
| `test_voice_doctor.py` | informe combinado de salud de voz |
| `test_voice_doctor_cli.py` | CLI `voice-doctor` |
| `test_voice_logs.py` | log JSONL de wake/app y comandos reconocidos |
| `test_voice_logs_cli.py` | CLI `voice-logs` para leer eventos recientes |
| `test_voice_modes.py` | ruteo de modos de voz |
| `test_voice_plan_cli.py` | CLI `voice-plan` para depurar planes IA |
| `test_voice_processes.py` | clasificacion de procesos wake/app y duplicados |
| `test_voice_send_cli.py` | CLI `voice-send` para mandar texto a Jarvis |
| `test_voice_start_cli.py` | CLI `voice-start` para arrancar wake en segundo plano |
| `test_voice_startup_cli.py` | CLI `voice-startup` para instalar arranque oculto en Windows |
| `test_voice_status_cli.py` | CLI `voice-status` para diagnostico |
| `test_voice_stop_cli.py` | CLI `voice-stop` con dry-run seguro |
| `test_voice_restart_cli.py` | CLI `voice-restart` para reinicio limpio |
| `test_wake_listener.py` | wake phrase, variantes y lanzamiento |

### Unit tests nuevos recomendados

- `test_process_lifecycle.py`
  - no permite dos wake listeners del mismo workspace.
  - `--stop` limpia wake y app hijas.
  - app viva recibe `show` en vez de abrir duplicado.
- `test_voice_latency.py`
  - ventana de escucha configurable.
  - valores invalidos usan default.
  - latencia simulada queda por debajo del limite esperado.
- `test_action_config.py`
  - lee acciones desde config.
  - valida rutas Windows.
  - rechaza comandos peligrosos sin confirmacion.
- `test_startup.py`
  - genera tarea/acceso directo de inicio.
  - desinstala startup sin dejar restos.
- `test_logs.py`
  - crea logs.
  - rota logs grandes.
  - no rompe si `logs/` no existe.
- `test_tts_interrupt.py`
  - `terminate()` mata TTS.
  - una generacion vieja no habla despues de cancelarse.
- `test_stt_aliases.py`
  - alias foneticos para "codu time".
  - alias foneticos para "quiero verte".
  - alias foneticos para "hola jarvis".

## Pruebas manuales obligatorias

### 1. Arranque limpio

Comandos:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet wake --stop
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet voice-start
```

Resultado esperado:

- Solo queda un wake listener.
- No aparece terminal extra en uso normal.
- No se abre la app hasta decir "Hola Jarvis".

### 2. Wake

Pasos:

- Decir "Hola Jarvis".

Resultado esperado:

- Se abre la app fullscreen.
- Jarvis dice "A ver, que deseas?".
- La UI muestra estado de micro abierto.

### 3. Mostrar/esconder

Pasos:

- Decir "escondete".
- Decir "quiero verte".

Resultado esperado:

- La app se oculta.
- El proceso sigue vivo.
- La app vuelve al frente al pedirlo.

### 4. Alt+Tab

Pasos:

- Con Jarvis visible, pulsar Alt+Tab hacia Chrome/Cursor.
- Hablar con Jarvis mientras otra ventana esta activa.
- Decir "quiero verte".

Resultado esperado:

- Jarvis no se cierra.
- Sigue escuchando.
- Vuelve a primer plano al pedirlo.

### 5. Interrupcion de voz

Pasos:

- Preguntar algo que genere respuesta larga.
- Mientras habla, decir "callate".
- Repetir y decir una nueva orden mientras habla.

Resultado esperado:

- La voz se corta.
- No responde "vale" ni otra frase al pedir silencio.
- La nueva orden tiene prioridad.

### 6. Codu time

Pasos:

- Decir "codu time".
- Probar variantes:
  - "code time".
  - "codi time".
  - "codu taim".

Resultado esperado:

- Chrome abre el perfil de `info@coduworks.com`.
- Abre `https://monitoring.coduworks.com/`.
- Abre la vista Notion configurada.
- Cursor abre `C:\Users\dani2\github\C4-KNX`.
- Chrome queda en el 50% izquierdo de pantalla.
- Cursor queda en el 50% derecho de pantalla.
- Docker Desktop se abre.
- `docker-compose.dev.yml` se levanta en segundo plano.
- No abre duplicados innecesarios si ya estaban abiertos.

### 7. Cierre

Pasos:

- Decir "adios Jarvis".

Resultado esperado:

- La app se cierra.
- El wake listener sigue vivo.
- Al decir "Hola Jarvis" vuelve a abrirse.

### 8. Reinicio del PC

Pasos:

- Activar startup cuando este implementado.
- Reiniciar Windows.
- No tocar nada.
- Decir "Hola Jarvis".

Resultado esperado:

- Wake listener esta en segundo plano.
- La app no aparece hasta wake.
- No hay procesos duplicados.

## Pruebas de rendimiento

### Metricas a medir

- Tiempo desde "Hola Jarvis" hasta ventana visible.
- Tiempo desde final de frase hasta transcript final.
- Tiempo desde transcript hasta respuesta Codex.
- Tiempo desde respuesta Codex hasta inicio de TTS.
- FPS medio de particulas.
- CPU/RAM en idle.
- CPU/RAM escuchando.
- CPU/RAM procesando.

### Objetivos

| Metrica | Objetivo |
| --- | --- |
| Wake a ventana visible | < 2.5 s |
| Orden corta reconocida | < 3.5 s |
| Accion local ejecutada | < 1.5 s tras STT |
| Inicio de TTS tras respuesta | < 0.5 s |
| UI idle | estable, sin lag visible |
| Procesos duplicados | 0 |

## Pruebas de regresion

Antes de dar por buena cualquier mejora:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes
```

Checklist:

- Wake sigue funcionando.
- "quiero verte" sigue funcionando.
- "escondete" sigue funcionando.
- "callate" corta TTS.
- `codu time` sigue funcionando.
- No pide `OPENAI_API_KEY` si motor es Codex.
- No queda terminal visible.
- No quedan procesos duplicados.

## Pruebas de procesos

Listar procesos Jarvis:

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and
    $_.CommandLine -like '*openjarvis.cli*'
  } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine |
  Format-List
```

Resultado esperado:

- Un arbol wake.
- Cero o un arbol app.
- No varias apps abiertas a la vez.

Parar wake:

```powershell
.\.venv\Scripts\python.exe -m openjarvis.cli --quiet wake --stop
```

## Criterios de aceptacion

Jarvis esta correcto cuando:

- Al decir "Hola Jarvis" aparece siempre.
- Al decir "quiero verte" aparece si estaba escondido.
- Alt+Tab no cierra la app.
- Mientras habla, puedes cortarlo.
- `codu time` ejecuta la rutina completa.
- Los tests pasan.
- No hay procesos repetidos.
- No hay dependencia de `OPENAI_API_KEY` para el motor Codex CLI.
- La UI se ve fluida y limpia.

## Roadmap recomendado

### Fase 1 - Estabilidad

- `jarvis status`.
- `jarvis restart-voice`.
- logs rotativos.
- tests de ciclo de procesos.
- corregir duplicados definitivamente.

### Fase 2 - Voz rapida

- VAD local.
- STT streaming o ventanas dinamicas.
- alias foneticos ampliados.
- medicion de latencia.

### Fase 3 - Acciones configurables

- archivo de acciones.
- editor simple de acciones.
- confirmaciones de seguridad.
- mas rutinas tipo `codu time`.

### Fase 4 - UI pulida

- FPS adaptativo.
- particulas escalables.
- panel debug opcional.
- historial compacto de conversacion.

### Fase 5 - Arranque con Windows

- instalar/desinstalar startup.
- monitor de salud.
- reinicio automatico controlado.

## Notas de seguridad

- No ejecutar comandos destructivos sin confirmacion.
- No cerrar procesos que no sean de Jarvis.
- No abrir archivos sensibles sin pedir permiso si la orden no es clara.
- No guardar claves en texto plano.
- No depender de variables `OPENAI_API_KEY` para el modo Codex CLI.
- Mantener acciones locales configurables y revisables.

## Ajuste 2026-05-05 - Workflows y nombres propios

Problema visto en logs:

- `Ditelba` se transcribia como `vitelva`, `vitelba`, `ditelva` o `delvano`.
- `HGR` se transcribia como `HFR` o `hache ge erre`.
- `Conectate a vitelva` iba a chat/Codex y tardaba unos 16 segundos, cuando debia ser accion local.
- `Que tres proyectos tienes` dependia del modelo aunque la UI ya conoce las orbitas.

Cambios:

- Hotwords y prompt de Whisper ampliados con `Ditelba`, `Codu`, `HGR` y `hache ge erre`.
- Correccion local de STT para convertir aliases recientes a `Ditelba` y `HGR`.
- Accion local para `conectate a Ditelba`, `conectate a HGR` y `conectate a Codu`.
- Respuesta local para listar flujos: `Ditelba`, `Codu` y `HGR`.
- Prompt de Codex enriquecido con los workflows conocidos para que no invente ni cambie nombres si una frase cae en chat.

Pruebas especificas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes\test_local_stt.py tests\voice_modes\test_local_actions.py tests\voice_modes\test_codex_cli.py
.\.venv\Scripts\python.exe -m pytest tests\voice_modes
.\.venv\Scripts\python.exe -m openjarvis.cli voice-restart
.\.venv\Scripts\python.exe -m openjarvis.cli voice-status
```

## Ajuste 2026-05-05 - Orbitas de proyectos y contexto constante

Cambios:

- Los proyectos se han centralizado en `openjarvis.workflows` para que UI, acciones locales, Codex y planner usen la misma lista.
- Jarvis conoce siempre estos 3 flujos: `Ditelba`, `Codu` y `HGR`.
- La UI marca el workflow activo como `TRABAJANDO` y lo pinta en verde.
- Las orbitas laterales ahora se dibujan como miniesferas de particulas, en el mismo estilo visual que la esfera principal.
- `conectate a ...`, `modo ...` y `trabaja en ...` actualizan el workflow activo.
- El contexto de workflows entra en `voice-context`, en el prompt de Codex y en el prompt del planner de acciones.

Pruebas especificas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes\test_workflows.py tests\voice_modes\test_desktop_voice_app.py tests\voice_modes\test_local_actions.py tests\voice_modes\test_codex_cli.py tests\voice_modes\test_computer_context.py tests\voice_modes\test_voice_action_plan.py
```

## Ajuste 2026-05-05 - Precision STT restaurada

Problema visto en logs:

- El comando STT estaba usando `whisper/base` para ganar velocidad.
- Frases con `HGR` y `hache ge erre` se degradaban, por ejemplo `Quiero drogar al edad seferre`.
- Tras una respuesta hablada podia entrar cola de TTS como si fuera una orden nueva.

Cambios:

- El modelo automatico de comandos ahora prefiere `whisper/small` si esta en cache.
- `beam_size` y `best_of` por defecto suben a `5` para mejorar transcripcion en espanol.
- La ventana dinamica da mas margen: silencio de comando `1.45s` y maximo `6.8s`.
- Se anade una pausa post-TTS de `450ms` antes de volver a escuchar para evitar eco de la voz de Jarvis.
- Correcciones STT nuevas: `edad seferre` y variantes pasan a `HGR`; el caso real del log pasa a `quiero trabajar en hgr`.
- Los dispositivos que entregan audio digitalmente muerto (`RMS=0`) se marcan como fallidos temporalmente para evitar que Jarvis se quede escuchando un micro virtual sin senal.

Pruebas especificas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes\test_local_stt.py tests\voice_modes\test_desktop_voice_app.py tests\voice_modes\test_local_actions.py
.\.venv\Scripts\python.exe -m pytest tests\voice_modes
```

## Comando de validacion rapida

```powershell
.\.venv\Scripts\python.exe -m pytest tests\voice_modes
Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and
    $_.CommandLine -like '*openjarvis.cli*'
  } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine |
  Format-List
```
