import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const isWeb = Platform.OS === "web";

function getWebStorage(): Storage | null {
  if (typeof localStorage === "undefined") {
    return null;
  }
  return localStorage;
}

export const storage = {
  async set(key: string, value: string) {
    if (isWeb) {
      const webStorage = getWebStorage();
      if (webStorage) {
        webStorage.setItem(key, value);
      }
      return;
    }

    await SecureStore.setItemAsync(key, value);
  },

  async get(key: string) {
    if (isWeb) {
      const webStorage = getWebStorage();
      return webStorage ? webStorage.getItem(key) : null;
    }

    return await SecureStore.getItemAsync(key);
  },

  async remove(key: string) {
    if (isWeb) {
      const webStorage = getWebStorage();
      if (webStorage) {
        webStorage.removeItem(key);
      }
      return;
    }

    await SecureStore.deleteItemAsync(key);
  },
};
