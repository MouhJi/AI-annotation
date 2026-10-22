import type {DraftAnnotation} from "../types";

export const annotatorName = (annotation: DraftAnnotation) => annotation.isNew ? "Unsaved" : annotation.created_by?.full_name || "Unknown annotator";
export const annotationLabel = (annotation: DraftAnnotation) => `${annotation.class_name || "Unknown class"} · ${annotatorName(annotation)}`;
const date = (value?: string) => value ? new Date(value).toLocaleString() : "Unknown";

export default function AnnotationAttribution({annotation}: {annotation: DraftAnnotation}) {
  return <section className="annotation-details" aria-label="Object details" style={{overflowWrap:"anywhere"}}>
    <h3>Object details</h3>
    <p>Class: {annotation.class_name}</p>
    <p>Created by: {annotatorName(annotation)}</p>
    <p>Created at: {annotation.isNew ? "Not saved yet" : date(annotation.created_at)}</p>
    <p>Last edited by: {annotation.isNew ? "Unsaved" : annotation.updated_by?.full_name || "Unknown annotator"}</p>
    <p>Last edited at: {annotation.isNew ? "Not saved yet" : date(annotation.updated_at)}</p>
    <p>Source: {annotation.source === "ai_accepted" ? "AI-assisted (YOLO)" : annotation.source === "legacy" ? "Legacy annotation" : "Manual"}</p>
  </section>;
}
