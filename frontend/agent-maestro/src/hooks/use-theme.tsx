import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "dark" | "light" | "frappe" | "blue" | "orange" | "rose";

const THEMES: { value: Theme; label: string; preview: string }[] = [
  { value: "dark", label: "Dark", preview: "hsl(228, 12%, 8%)" },
  { value: "light", label: "Light", preview: "hsl(0, 0%, 98%)" },
  { value: "frappe", label: "Frappé", preview: "hsl(229, 19%, 18%)" },
  { value: "blue", label: "Blue", preview: "hsl(222, 20%, 8%)" },
  { value: "orange", label: "Orange", preview: "hsl(20, 14%, 8%)" },
  { value: "rose", label: "Rose", preview: "hsl(340, 12%, 8%)" },
];

const ACCENT_COLORS: Record<Theme, string> = {
  dark: "hsl(142, 72%, 50%)",
  light: "hsl(142, 72%, 40%)",
  frappe: "hsl(267, 84%, 75%)",
  blue: "hsl(210, 100%, 56%)",
  orange: "hsl(25, 95%, 55%)",
  rose: "hsl(340, 82%, 60%)",
};

type ThemeContextType = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  themes: typeof THEMES;
  accentColors: typeof ACCENT_COLORS;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem("ocin-theme") as Theme) || "dark";
  });

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem("ocin-theme", t);
  };

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES, accentColors: ACCENT_COLORS }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
