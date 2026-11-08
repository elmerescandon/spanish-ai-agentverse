import type { FieldChange, ProtocolField } from "@/lib/api";

export interface FieldSection {
  key: string;
  title: string;
  fields: ProtocolField[];
}

// Fields with no "section." prefix are listed under this heading.
const UNSECTIONED_KEY = "general";

/** "hba1c_upper_bound" → "Hba1c upper bound": stored names read as text. */
export function humanizeName(name: string): string {
  const text = name.replaceAll("_", " ").replaceAll(".", " · ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function splitField(field: string): [section: string, name: string] {
  const dot = field.indexOf(".");
  return dot < 0
    ? [UNSECTIONED_KEY, field]
    : [field.slice(0, dot), field.slice(dot + 1)];
}

/** The field's name inside its section, as readable text. */
export function fieldLabel(field: string): string {
  return humanizeName(splitField(field)[1]);
}

/** Fields grouped by their "section." prefix, in first-seen order. */
export function groupFieldsBySection(
  fields: readonly ProtocolField[]
): FieldSection[] {
  const sections = new Map<string, ProtocolField[]>();
  for (const field of fields) {
    const [key] = splitField(field.field);
    sections.set(key, [...(sections.get(key) ?? []), field]);
  }
  return [...sections].map(([key, sectionFields]) => ({
    key,
    title: humanizeName(key),
    fields: sectionFields,
  }));
}

/** Names of the fields a reviewer changed at least once. */
export function changedFieldNames(
  changes: readonly FieldChange[]
): Set<string> {
  return new Set(changes.map((change) => change.field));
}
