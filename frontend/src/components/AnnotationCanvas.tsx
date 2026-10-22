import ProtectedImage from "./ProtectedImage";
import {annotationLabel} from "./AnnotationAttribution";
import { useEffect, useState, type MouseEvent as ReactMouseEvent } from "react";
import type { DraftAnnotation, LabelClass, Point, Prediction } from "../types";
import "./AnnotationCanvas.css";

type Props = {
  readOnly?: boolean;
  src: string; imageWidth: number; imageHeight: number; annotations: DraftAnnotation[]; classes: LabelClass[]; predictions?: Prediction[]; selected?: number; selectedPrediction?: number; classId?: number; mode: "select" | "draw" | "polygon";
  onSelect: (id?: number) => void; onSelectPrediction?: (id: number) => void; onAdd: (annotation: Omit<DraftAnnotation, "id" | "isNew">) => void; onChange: (id: number, annotation: Partial<DraftAnnotation>) => void;
};
type Dimensions = { width: number; height: number };
const colors = ["#38bdf8", "#f97316", "#a78bfa", "#22c55e", "#f43f5e"];
const numberOr = (value: unknown, fallback = 0) => { const number = Number(value); return Number.isFinite(number) ? number : fallback; };
const validPoints = (value: unknown): Point[] => !Array.isArray(value) ? [] : value.flatMap((point): Point[] => {
  if (!Array.isArray(point) || point.length < 2) return [];
  const x = Number(point[0]); const y = Number(point[1]);
  return Number.isFinite(x) && Number.isFinite(y) ? [[x, y]] : [];
});
const pointsAttribute = (points: Point[]) => points.map(([x, y]) => `${x},${y}`).join(" ");
const dedupePolygonPoints = (points: Point[]) => {
  const cleaned = points.filter((point, index) => index === 0 || Math.hypot(point[0] - points[index - 1][0], point[1] - points[index - 1][1]) > 0.5);
  const last = cleaned[cleaned.length - 1];
  if (cleaned.length > 1 && Math.hypot(cleaned[0][0] - last[0], cleaned[0][1] - last[1]) <= 0.5) cleaned.pop();
  return cleaned;
};

/** SVG avoids react-konva's separate reconciler and remains fully usable for labeling. */
export default function AnnotationCanvas(props: Props) {
  const [image, setImage] = useState<Dimensions>();
  const [failed, setFailed] = useState(false);
  const [drawStart, setDrawStart] = useState<Point | null>(null);
  const [temporaryBox, setTemporaryBox] = useState<{ x: number; y: number; width: number; height: number } | null>(null);
  const [draft, setDraft] = useState<Point[]>([]);
  const classes = Array.isArray(props.classes) ? props.classes : [];
  const annotations = Array.isArray(props.annotations) ? props.annotations : [];
  const predictions = Array.isArray(props.predictions) ? props.predictions : [];

  useEffect(() => { setImage(undefined); setFailed(false); setDrawStart(null); setTemporaryBox(null); setDraft([]); }, [props.src]);
  useEffect(() => { if (props.mode !== "polygon") setDraft([]); }, [props.mode]);

  const scale = image ? Math.min(1, 900 / image.width, 620 / image.height) : 1;
  const displayWidth = image ? image.width * scale : 0;
  const displayHeight = image ? image.height * scale : 0;
  const pointFromEvent = (event: ReactMouseEvent<SVGSVGElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = rect.width ? (event.clientX - rect.left) * image!.width / rect.width : 0;
    const y = rect.height ? (event.clientY - rect.top) * image!.height / rect.height : 0;
    return [Math.max(0, Math.min(image!.width, x)), Math.max(0, Math.min(image!.height, y))];
  };
  function finishPolygon() {
    if(props.readOnly)return;
    const points = dedupePolygonPoints(draft);
    if (points.length < 3) { setDraft([]); return; }
    const selectedClass = classes.find((item) => item.id === props.classId);
    if (!selectedClass) { alert("Please select a class first."); return; }
    const xs = points.map(([x]) => x), ys = points.map(([, y]) => y);
    props.onAdd({ class_id: selectedClass.id, class_name: selectedClass.name, annotation_type: "polygon", points, x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) });
    setDraft([]); props.onSelect(undefined);
  }
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (props.mode !== "polygon") return;
      if (event.key === "Escape") { setDraft([]); event.preventDefault(); }
      if (event.key === "Enter") { finishPolygon(); event.preventDefault(); }
    };
    window.addEventListener("keydown", onKeyDown); return () => window.removeEventListener("keydown", onKeyDown);
  }, [props.mode, draft, props.classId, classes]);
  if (!image) return <div className="canvas"><ProtectedImage className="canvas-loader" src={props.src} alt="" onLoad={(event) => setImage({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} onError={() => setFailed(true)} />{failed ? "Unable to load this image file." : "Loading image…"}</div>;

  const finishBox = () => {
    if (props.readOnly || !drawStart || !temporaryBox) return;
    const selectedClass = classes.find((item) => item.id === props.classId);
    if (temporaryBox.width > 2 && temporaryBox.height > 2 && selectedClass) props.onAdd({ class_id: selectedClass.id, class_name: selectedClass.name, annotation_type: "bbox", points: null, ...temporaryBox });
    setDrawStart(null); setTemporaryBox(null);
  };
  return <div className="canvas"><div className="annotation-surface" style={{ width: displayWidth, height: displayHeight }}><ProtectedImage src={props.src} alt="Annotation target" draggable={false}/><svg viewBox={`0 0 ${image.width} ${image.height}`} onMouseDown={(event) => {
    if(props.readOnly)return;
    if (props.mode === "draw") {
      if (!classes.some((item) => item.id === props.classId)) { alert("Please select a class first."); return; }
      const point = pointFromEvent(event); setDrawStart(point); setTemporaryBox({ x: point[0], y: point[1], width: 0, height: 0 });
    } else if (props.mode === "polygon") {
      if (!classes.some((item) => item.id === props.classId)) { alert("Please select a class first."); return; }
      // Read the synthetic event before the state updater runs; React clears currentTarget afterwards.
      const point = pointFromEvent(event); setDraft((current) => [...current, point]);
    }
  }} onDoubleClick={(event) => { if (!props.readOnly && props.mode === "polygon") { event.preventDefault(); finishPolygon(); } }} onMouseMove={(event) => {
    if (props.readOnly || !drawStart) return; const [x, y] = pointFromEvent(event); setTemporaryBox({ x: Math.min(x, drawStart[0]), y: Math.min(y, drawStart[1]), width: Math.abs(x - drawStart[0]), height: Math.abs(y - drawStart[1]) });
  }} onMouseUp={finishBox}>
    {annotations.map((annotation, index) => {
      const id = numberOr(annotation.id, -index - 1), classIndex = classes.findIndex((item) => item.id === annotation.class_id), color = colors[classIndex >= 0 ? classIndex % colors.length : 0];
      const points = validPoints(annotation.points), polygon = annotation.annotation_type === "polygon" && points.length >= 3, x = numberOr(annotation.x), y = numberOr(annotation.y), width = Math.max(0, numberOr(annotation.width)), height = Math.max(0, numberOr(annotation.height));
      const select = (event: ReactMouseEvent<SVGElement>) => { event.stopPropagation(); props.onSelect(id); };
      const fullLabel = annotationLabel(annotation), maxChars = Math.max(8, Math.min(44, Math.floor(displayWidth / 8)));
      const label = Array.from(fullLabel).length > maxChars ? Array.from(fullLabel).slice(0, maxChars - 1).join("") + "…" : fullLabel;
      const labelWidth = Math.min(image.width, (Array.from(label).length * 8 + 10) / scale);
      const labelX = Math.max(0, Math.min(x, image.width - labelWidth));
      const labelY = Math.min(image.height - 18 / scale, Math.max(0, y - 22 / scale));
      return <g key={`annotation-${id}`} onMouseDown={select}><title>{fullLabel}</title>{polygon ? <polygon points={pointsAttribute(points)} fill={color} fillOpacity="0.18" stroke={color} strokeWidth={props.selected === id ? 3 / scale : 2 / scale}/> : <rect x={x} y={y} width={width} height={height} fill="transparent" stroke={color} strokeWidth={props.selected === id ? 3 / scale : 2 / scale}/>}<g pointerEvents="none"><rect x={labelX} y={labelY} width={labelWidth} height={20 / scale} rx={3 / scale} fill="#0f172a" fillOpacity="0.9"/><text x={labelX + 4 / scale} y={labelY + 14 / scale} fill={color} fontSize={13 / scale}>{label}</text></g></g>;
    })}
    {predictions.filter((prediction) => prediction.status === "PENDING").map((prediction, index) => {
      const id = numberOr(prediction.id, -100000 - index), points = validPoints(prediction.points), polygon = prediction.prediction_type === "polygon" && points.length >= 3, x = numberOr(prediction.x), y = numberOr(prediction.y), stroke = props.selectedPrediction === id ? "#facc15" : "#ec4899", confidence = numberOr(prediction.confidence);
      return <g key={`prediction-${id}`} onMouseDown={(event) => { event.stopPropagation(); props.onSelectPrediction?.(id); }}>{polygon ? <polygon points={pointsAttribute(points)} fill="#ec4899" fillOpacity="0.1" stroke={stroke} strokeWidth={2 / scale} strokeDasharray={`${8 / scale} ${5 / scale}`}/> : <rect x={x} y={y} width={Math.max(0, numberOr(prediction.width))} height={Math.max(0, numberOr(prediction.height))} fill="transparent" stroke={stroke} strokeWidth={2 / scale} strokeDasharray={`${8 / scale} ${5 / scale}`}/>}<text x={x} y={Math.max(0, y - 6 / scale)} fill="#ec4899" fontSize={14 / scale}>{`${typeof prediction.model_class_name === "string" ? prediction.model_class_name : "Prediction"} ${(confidence * 100).toFixed(0)}%`}</text></g>;
    })}
    {temporaryBox && <rect {...temporaryBox} fill="transparent" stroke="#eab308" strokeWidth={2 / scale} strokeDasharray={`${6 / scale} ${4 / scale}`}/>} {draft.length > 0 && <><polyline points={pointsAttribute(draft)} fill="none" stroke="#eab308" strokeWidth={2 / scale} strokeDasharray={`${6 / scale} ${4 / scale}`}/>{draft.map(([x, y], index) => <circle key={`draft-${index}`} cx={x} cy={y} r={4 / scale} fill="#eab308"/>)}</>}
  </svg></div><small>{Math.round(image.width)} × {Math.round(image.height)} · {Math.round(scale * 100)}% {props.mode === "polygon" && "· click vertices, double-click or Finish to complete"}</small>{!props.readOnly && props.mode === "polygon" && <span className="canvas-actions"><button onClick={finishPolygon}>Finish polygon</button><button onClick={() => setDraft([])}>Cancel</button></span>}</div>;
}
