const DEV_EMAILS = (import.meta.env.VITE_DEVELOPER_EMAILS as string | undefined)
  ?.split(',')
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean) ?? [];

export const isDeveloper = (email?: string | null): boolean =>
  !!email && DEV_EMAILS.includes(email.toLowerCase());
