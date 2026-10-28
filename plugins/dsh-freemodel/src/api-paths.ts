/**
 * Route constants shared by the host-side local API and the browser card.
 *
 * Kept in a Node-free module so the client bundle can import them without
 * pulling `node:crypto` or the status reader into the browser.
 */

/** Route prefix registered with the host web server. */
export const API_PREFIX = "/freemodel/api";
/** Request header carrying the write token / secret. */
export const SECRET_HEADER = "x-freemodel-secret";

export const STATUS_PATH = `${API_PREFIX}/status`;
export const REFRESH_PATH = `${API_PREFIX}/refresh`;
export const TEST_PATH = `${API_PREFIX}/test`;