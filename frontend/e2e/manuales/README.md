# Pruebas manuales del reproductor (contra el servidor de verdad)

Estos dos guiones **no** son pruebas de Playwright normales (`*.spec.ts`, que se ejecutan con
`yarn test:e2e` contra un servidor local en `127.0.0.1:4173`). Son guiones suelos que se
ejecutan **a mano contra el servidor de verdad**, porque lo que comprueban (audio real,
canciones que existen o no en el disco del servidor, pantalla táctil) no se puede simular con
un servidor de mentira.

Se dejaron aquí y no en `_deploy/` porque ese directorio está en `.gitignore` y se perdían.

## Cómo se ejecutan

```bash
cd frontend/e2e/manuales
npm install playwright        # solo la primera vez (los navegadores ya suelen estar)
node probar-reproduccion.js   # móvil emulado 390x844, táctil
node probar-escritorio.js     # escritorio 1440x900, con ratón
```

La URL por defecto es `http://servidor:8090` (el nombre de Tailscale). Para apuntar a otro
sitio:

```bash
URL=http://127.0.0.1:8090 node probar-reproduccion.js
```

## Qué comprueba cada uno

`probar-reproduccion.js` (30 comprobaciones):

1. Crea una playlist **con canciones que sí tienen archivo**, comprobándolo una a una contra
   `/stream` (el catálogo tiene más canciones que ficheros, así que hay que verificarlo).
2. Reproduce con el botón grande y comprueba que **el tiempo avanza** y que la página no se
   queda en blanco.
3. Barra de progreso: que exista, que tenga tamaño y que **al tocarla busque** dentro de la
   canción.
4. Play/pausa en los **dos** sentidos; siguiente y anterior.
5. Aleatorio: encender **y apagar**.
6. Repetición: los tres estados (apagado, contexto, una sola canción).
7. Volumen: que cambie el volumen real del audio y que se recuerde.
8. Una canción **sin archivo**: que avise en pantalla y salte a la siguiente, en vez de
   quedarse clavada.

`probar-escritorio.js` (17 comprobaciones): lo mismo sobre la barra de abajo del escritorio,
incluido el **arrastre real con el ratón** en la barra de progreso.

`probar-listas.js` (21 comprobaciones): el **ciclo de vida completo de una lista por la
interfaz**, en móvil emulado. Crear con canciones → abrir → renombrar → **poner foto** →
comprobar que la pantalla se repinta → **hacer pública y volver a privada** → reproducir →
borrar (comprobando que **pregunta** y que cancelar no borra). Cada paso se verifica **contra
la API**, no contra lo que dice la pantalla, y además se comprueba que los avisos salen y que
la foto **se carga de verdad** (`naturalWidth > 0`): un `<img>` con la dirección correcta pero
la imagen rota pasaría una comprobación ingenua, y de hecho pasó.

> Los guiones crean usuarios, playlists y canciones de prueba (`*@radiopv-test.com`) en el
> servidor. **Bórralos después de cada tanda**, porque sus reproducciones entran en la
> popularidad, en las tendencias y en los mixes que ve el usuario de verdad:
>
> ```bash
> # Primero informa; con --apply borra (usuarios, sus listas, reproducciones, reacciones…)
> docker exec radiopv-api python /app/scripts/limpiar_datos_de_prueba.py
> docker exec radiopv-api python /app/scripts/limpiar_datos_de_prueba.py --apply
> ```
