import { getColor } from 'colorthief';

/* eslint-disable eqeqeq */
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'Anonymous';
    img.addEventListener('load', () => {
      resolve(img);
    });
    // `reject` a secas rechazaba con el EVENTO de error, no con un Error: quien no capturase la
    // promesa se quedaba con un «Uncaught (in promise) Event» sin mensaje ni pista de qué imagen
    // había fallado. Y falla de verdad: cualquier carátula que no cargue (o una ruta servida mal)
    // acaba aquí.
    img.addEventListener('error', () =>
      reject(new Error(`No se ha podido cargar la imagen para analizar su color: ${src}`))
    );
    img.src = src;
  });
}

function getAverageRGB(imgEl: HTMLImageElement) {
  var blockSize = 5, // only visit every 5 pixels
    defaultRGB = { r: 0, g: 0, b: 0 }, // for non-supporting envs
    canvas = document.createElement('canvas'),
    context = canvas.getContext && canvas.getContext('2d'),
    data,
    width,
    height,
    i = -4,
    length,
    rgb = { r: 0, g: 0, b: 0 },
    count = 0;

  if (!context) {
    return defaultRGB;
  }

  height = canvas.height = imgEl.naturalHeight || imgEl.offsetHeight || imgEl.height;
  width = canvas.width = imgEl.naturalWidth || imgEl.offsetWidth || imgEl.width;

  context.drawImage(imgEl, 0, 0);

  try {
    data = context.getImageData(0, 0, width, height);
  } catch (e) {
    /* security error, img on diff domain */
    return defaultRGB;
  }

  length = data.data.length;

  while ((i += blockSize * 4) < length) {
    ++count;
    rgb.r += data.data[i];
    rgb.g += data.data[i + 1];
    rgb.b += data.data[i + 2];
  }

  // ~~ used to floor values
  rgb.r = ~~(rgb.r / count);
  rgb.g = ~~(rgb.g / count);
  rgb.b = ~~(rgb.b / count);
  return rgb;
}

function componentToHex(c: any) {
  var hex = c.toString(16);
  return hex.length == 1 ? '0' + hex : hex;
}

function rgbToHex(r: number, g: number, b: number) {
  return '#' + componentToHex(r) + componentToHex(g) + componentToHex(b);
}

const COLOR_POR_DEFECTO = '#000000';

/**
 * Color medio de una imagen, para pintar el degradado de la cabecera.
 *
 * **Nunca lanza.** Antes, si la imagen no cargaba, la promesa se rechazaba y —como los 13 sitios
 * que la llaman hacen `.then(...)` sin `.catch(...)`— salía un `Uncaught (in promise) Event` en la
 * consola. Con una carátula rota se llenaba la consola de ruido y, de paso, el color de la página
 * se quedaba a medias sin que nadie lo supiera. Aquí no hay nada que el que llama pueda hacer al
 * respecto: si no se puede analizar, se devuelve el color por defecto y se avisa en la consola.
 */
export const getImageAnalysis = async (src: string): Promise<string> => {
  try {
    const img = await loadImage(src);
    const response = getAverageRGB(img);
    return rgbToHex(response.r, response.g, response.b);
  } catch (e) {
    console.warn(e);
    return COLOR_POR_DEFECTO;
  }
};

export const getImageAnalysis2 = async (src: string): Promise<string> => {
  try {
    const img = await loadImage(src);
    const color = await getColor(img);
    return color?.hex() ?? COLOR_POR_DEFECTO;
  } catch (e) {
    console.warn(e);
    return COLOR_POR_DEFECTO;
  }
};
