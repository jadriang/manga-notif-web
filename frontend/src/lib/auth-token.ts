type TokenGetter = () => Promise<string | null>;

let getter: TokenGetter | null = null;

export function registerTokenGetter(fn: TokenGetter) {
  getter = fn;
}

export async function getAuthToken(): Promise<string | null> {
  if (!getter) return null;
  return getter();
}
