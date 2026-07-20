export type ThemeMode = "light" | "dark";

export interface Account {
  id: string;
  name: string;
  email?: string;
  is_platform_admin: boolean;
}

export interface AuthResponse {
  token: string;
  account: Account;
}

export interface SkillFile {
  path: string;
  content: string;
}

export interface SkillData {
  slug: string;
  name: string;
  icon: string;
  category: string;
  description: string;
  instructions: string;
  tools: string[];
  files: SkillFile[];
  source: string;
}

export interface CatalogItem<T> {
  id: string;
  category: string;
  kind: string;
  data: T;
  sort: number;
  enabled: boolean;
  version: number;
  created_at?: number;
  updated_at?: number;
}

export interface SkillTool {
  name: string;
  label?: string;
  description?: string;
  min_app_version?: string;
}
