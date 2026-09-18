// Tiny IndexedDB key/value store used to cache Spotify GET responses across reloads and
// across pages. Kept dependency-free and fully fault-tolerant: every operation swallows its
// own errors (e.g. private-mode with IndexedDB disabled) so a cache failure never breaks a
// request — callers just fall through to the network.

const DB_NAME = 'spotify-api-cache';
const STORE = 'responses';
// v2: en la v1 se llegaron a guardar RESPUESTAS DE BÚSQUEDA (ver `axios.ts`), incluidas las que
// devolvían «sin resultados». Servirlas durante 24 h hacía que el buscador pareciera roto aunque
// el servidor ya estuviera arreglado, así que al subir de versión se tira todo lo viejo.
const DB_VERSION = 2;

let dbPromise: Promise<IDBDatabase> | null = null;

const openDb = (): Promise<IDBDatabase> => {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      const store = db.objectStoreNames.contains(STORE)
        ? request.transaction!.objectStore(STORE)
        : db.createObjectStore(STORE);
      store.clear();          // empezar limpio al cambiar de versión
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
};

export interface CacheEntry<T = unknown> {
  data: T;
  expiry: number;
}

export const cacheGet = async <T>(key: string): Promise<CacheEntry<T> | undefined> => {
  try {
    const db = await openDb();
    return await new Promise<CacheEntry<T> | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get(key);
      req.onsuccess = () => resolve(req.result as CacheEntry<T> | undefined);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return undefined;
  }
};

export const cacheSet = async (key: string, entry: CacheEntry): Promise<void> => {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(entry, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    /* ignore — caching is best-effort */
  }
};
