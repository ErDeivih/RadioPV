# Instrucciones para el agente

> **Este fichero es un convenio de trabajo, no una descripción del proyecto.**
> Se lee siempre, antes que nada. Existe para que puedas mandarme un mensaje desde el móvil
> y yo me encargue del resto sin que tengas que ir detrás.

---

## La regla principal

**Cuando te pida un cambio, no me contestes y te quedes esperando: crea un `goal` y
termínalo.**

En la práctica, cada vez que recibas una petición de cambio (una mejora, un arreglo, algo
nuevo), haz esto **en este orden**:

1. **Entiende qué quiero.** Si de verdad falta un dato que no puedes deducir, pregunta una
   vez y en una sola pregunta. Si puedes deducirlo del código o del historial, no preguntes.

2. **Crea un goal** con el objetivo concreto y medible. No "mejorar X", sino "que X haga Y y
   los tests de Z sigan pasando". El goal es lo que hace que sigas trabajando por rondas
   hasta conseguirlo, en vez de pararte al primer mensaje.

3. **Mira qué tests existen YA** antes de tocar nada. Este proyecto no se toca a ciegas: si
   hay una suite, esa suite es el contrato.

4. **Implementa.**

5. **Ejecuta los tests.** Todos los que apliquen. Si algo se rompe, **arréglalo**. No me
   entregues algo con tests en rojo ni me pidas permiso para arreglarlo.

6. **No cierres el goal** hasta que los tests pasen. Si te bloqueas de verdad (falta algo que
   solo yo puedo darte), entonces sí: di exactamente qué necesitas y para qué.

7. **Al terminar, resume** en pocas líneas: qué cambió, qué ficheros, **qué tests corriste y
   que pasaron**. Sin esto no considero el trabajo terminado.

---

## Los tests de ESTE proyecto (RadioPV)

| Qué | Cómo |
|---|---|
| **Backend** (FastAPI) | `python -m pytest backend/tests -q` |
| **Frontend, unitarios** | `cd frontend && yarn test` (vitest) |
| **Frontend, compilación y tipos** | `cd frontend && yarn build` (hace `tsc --noEmit` + vite) |
| **End-to-end en navegador** | `cd frontend && yarn test:e2e` (Playwright) |
| **Pruebas propias del proyecto** | `scripts/` — hay muchas de verificación; mira cuál aplica |

**El mínimo antes de dar algo por terminado**: que compile y que pasen los unitarios.

- Tocar el **backend** → `pytest`.
- Tocar el **frontend** → `yarn test` **y** `yarn build` (el `build` también comprueba tipos).
- Tocar **algo que se ve en pantalla** → además, comprobarlo en un navegador de verdad. En
  `scripts/` ya hay pruebas con Playwright que sirven de ejemplo.

> **Ojo con el entorno**: el servidor no tiene Node. Si hay que compilar el frontend, se hace
> en el PC o dentro de su contenedor. El despliegue va por `git push`, no copiando ficheros.

---

## Si te mando una foto

Voy a mandarte fotos desde el móvil: capturas de pantalla, fotos de la pantalla del
ordenador, bocetos en papel, errores. **Míralas antes de responder.**

- Si es una **captura o un error**, saca de ahí el mensaje exacto y trabaja con él.
- Si es un **boceto o un diseño**, respeta la intención: colores, disposición, jerarquía.
- Si la foto **no se entiende**, pregunta. No adivines.
- Si en la foto aparece **texto**, léelo entero; el dato que importa suele estar en una esquina.

---

## Nada se rompe

- **Antes de dar algo por bueno, los tests.** Los que ya existen, no los que te inventes.
- Si un cambio **rompe un test**, la prioridad es el test. O se arregla el cambio, o se
  actualiza el test **explicando por qué** el comportamiento nuevo es el bueno.
- **Nunca borres ni desactives un test** para que pase.
- Si no hay test para lo que estás tocando, **escríbelo**.
- Cambios pequeños y verificables mejor que uno grande.

---

## Cómo trabajar en RadioPV

- **Antes de tocar, mira.** Este proyecto ya tiene muchísimo hecho. Busca si esa misma cosa ya
  está resuelta antes de escribir nada nuevo.
- **Los comentarios explican POR QUÉ, no QUÉ.** Aquí hay decisiones poco obvias documentadas
  (por qué la URL de la API es relativa, por qué el contenedor de la web usa red de host, por
  qué ciertos umbrales valen lo que valen). **Respétalas** y, si arreglas algo así, deja
  escrito el motivo para que nadie lo "arregle" otra vez.
- **Los umbrales y las medidas se miden, no se inventan.** Si tocas algo que compara audio o
  detecta coincidencias, vuelve a calibrarlo con las herramientas de `scripts/`.
- **Nada de datos inventados.** Si no sabes un valor, mídelo o pregúntalo.
- **Nada de secretos en el repositorio.** Ni claves, ni tokens.
- **Ojo con las rutas de Windows.** El código corre en Linux en el servidor: rutas relativas
  y separadores POSIX.

---

## Al desplegar

RadioPV corre en el servidor. El despliegue va por `git`:

1. Los cambios se suben con `git push`.
2. El servidor los recoge solo y **reconstruye lo que haga falta, incluido el frontend**
   (se compila dentro de un contenedor, no hace falta Node en el servidor).

**No hace falta entrar al servidor a copiar nada a mano.** Si algo necesita algo que no llega
por git, dímelo claramente.

---

## Resumen para ti, agente

> Petición → entender → **goal** → mirar tests → implementar → **pytest y yarn build** →
> arreglar lo que se rompa → resumir. Sin tests en verde no hay goal cerrado.
