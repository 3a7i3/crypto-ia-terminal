// WEB-01B PWA registration.
// Registration is production-only so the development server never acquires a
// persistent service worker that could obscure local frontend/API debugging.
export const PWA_SERVICE_WORKER_PATH = "/sw.js";
export const PWA_UPDATE_INTERVAL_MS = 15 * 60 * 1000;

export function canRegisterOperatorPwa(): boolean {
  return (
    import.meta.env.PROD &&
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    window.isSecureContext
  );
}

export function registerOperatorPwa(): void {
  if (!canRegisterOperatorPwa()) return;

  const register = async () => {
    // Reload only when an already-controlled page receives a replacement
    // worker. First installation remains non-disruptive; later deployments
    // deterministically activate the new shell after skipWaiting()/claim().
    const hadController = navigator.serviceWorker.controller !== null;
    let reloadingForUpdate = false;
    if (hadController) {
      navigator.serviceWorker.addEventListener(
        "controllerchange",
        () => {
          if (reloadingForUpdate) return;
          reloadingForUpdate = true;
          window.location.reload();
        },
        { once: true },
      );
    }

    try {
      const registration = await navigator.serviceWorker.register(PWA_SERVICE_WORKER_PATH, { scope: "/" });

      // Do not wait for a browser restart to discover a new shell version.
      // The worker itself uses skipWaiting() and deletes only old shell caches.
      await registration.update();

      window.setInterval(() => {
        void registration.update().catch((error) => {
          console.warn("WEB-01B PWA update check failed", error);
        });
      }, PWA_UPDATE_INTERVAL_MS);
    } catch (error) {
      // Registration failure must never create a synthetic success state.
      // Live-data clients continue using direct same-origin network fetches.
      console.warn("WEB-01B PWA registration failed", error);
    }
  };

  if (document.readyState === "complete") {
    void register();
  } else {
    window.addEventListener("load", () => void register(), { once: true });
  }
}
