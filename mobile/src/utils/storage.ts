import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

/**
 * Cross-platform storage utility for React Native and Expo Web.
 * Uses expo-secure-store on mobile and localStorage on web.
 */
export const storage = {
  /**
   * Save a string value to persistent storage.
   */
  async set(key: string, value: string): Promise<void> {
    try {
      if (Platform.OS === "web") {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(key, value);
        }
      } else {
        await SecureStore.setItemAsync(key, value);
      }
    } catch (error) {
      console.error(`[Storage] Failed to set ${key}:`, error);
    }
  },

  /**
   * Retrieve a string value from persistent storage.
   * Returns null if the key does not exist or if storage is unavailable.
   */
  async get(key: string): Promise<string | null> {
    try {
      if (Platform.OS === "web") {
        if (typeof localStorage !== "undefined") {
          return localStorage.getItem(key);
        }
        return null;
      }
      return await SecureStore.getItemAsync(key);
    } catch (error) {
      console.error(`[Storage] Failed to get ${key}:`, error);
      return null;
    }
  },

  /**
   * Remove a value from persistent storage.
   */
  async remove(key: string): Promise<void> {
    try {
      if (Platform.OS === "web") {
        if (typeof localStorage !== "undefined") {
          localStorage.removeItem(key);
        }
      } else {
        await SecureStore.deleteItemAsync(key);
      }
    } catch (error) {
      console.error(`[Storage] Failed to remove ${key}:`, error);
    }
  },
};
