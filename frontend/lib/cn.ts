import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合併並去重 Tailwind CSS 類別名稱 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
