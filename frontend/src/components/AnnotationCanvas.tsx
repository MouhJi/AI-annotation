import ProtectedImage from "./ProtectedImage";
import {annotationLabel} from "./AnnotationAttribution";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent } from "react";
import {moveGeometry} from './annotationGeometry';
import {centeredViewport, clampImagePoint, fitViewport, resizedViewport, screenToImage, zoomViewport, type Dimensions, type Viewport} from './annotationViewport';
import type { DraftAnnotation, LabelClass, Point, Prediction } from "../types";
import "./AnnotationCanvas.css";

type Props = {
  readOnly?: boolean;
  resetViewportKey?: number;
  src: string; imageWidth: number; imageHeight: number; annotations: DraftAnnotation[]; classes: LabelClass[]; predictions?: Prediction[]; selected?: number; selectedPrediction?: number; classId?: number; mode: "select" | "draw" | "polygon";
  onSelect: (id?: number) => void; onSelectPrediction?: (id: number) => void; onAdd: (annotation: Omit<DraftAnnotation, "id" | "isNew">) => void; onChange: (id: number, annotation: Partial<DraftAnnotation>) => void;
};
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

/** Keep every persisted geometry in natural image pixels; only this viewport transforms. */
export default function AnnotationCanvas(props: Props) {
  const workspaceRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef(props.src);
  sourceRef.current = props.src;
  const [loaded, setLoaded] = useState<Dimensions & {src: string}>();
  const image = loaded?.src === props.src ? loaded : undefined;
  const imageRef = useRef<Dimensions>();
  imageRef.current = image;
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<Viewport>({scale: 1, offsetX: 0, offsetY: 0});
  const viewRef = useRef(view);
  const sizeRef = useRef<Dimensions>({width: 0, height: 0});
  const fitMode = useRef(true);
  const space = useRef(false), hovering = useRef(false);
  const [spaceHeld, setSpaceHeld] = useState(false), [panning, setPanning] = useState(false);
  const [editing, setEditing] = useState(false);
  const pan = useRef<{start: Point; view: Viewport; pointerId: number} | null>(null);
  const box = useRef<{start: Point; pointerId: number} | null>(null);
  const gesture = useRef<{annotation: DraftAnnotation; start: Point; handle: string; vertex?: number; pointerId: number} | null>(null);
  const [temporaryBox, setTemporaryBox] = useState<{x: number; y: number; width: number; height: number} | null>(null);
  const [draft, setDraft] = useState<Point[]>([]);
  const classes = Array.isArray(props.classes) ? props.classes : [];
  const annotations = Array.isArray(props.annotations) ? props.annotations : [];
  const predictions = Array.isArray(props.predictions) ? props.predictions : [];
  const editable = (a: DraftAnnotation) => !props.readOnly && props.mode === 'select' && (a.isNew || a.can_edit === true);
  const updateView = (next: Viewport) => {viewRef.current = next; setView(next);};
  const localPoint = (event: {clientX: number; clientY: number}): Point => {
    const rect = workspaceRef.current!.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };
  const pointerPoint = (event: {clientX: number; clientY: number}): Point =>
    clampImagePoint(screenToImage(localPoint(event), viewRef.current), imageRef.current!);
  const reset = (fit: boolean) => {
    if (!imageRef.current) return;
    fitMode.current = fit;
    updateView(fit ? fitViewport(imageRef.current, sizeRef.current) : centeredViewport(imageRef.current, sizeRef.current));
  };
  const zoom = (factor: number, anchor: Point = [sizeRef.current.width / 2, sizeRef.current.height / 2]) => {
    if (!imageRef.current || pan.current || gesture.current || box.current) return;
    fitMode.current = false;
    updateView(zoomViewport(viewRef.current, anchor, viewRef.current.scale * factor, imageRef.current, sizeRef.current));
  };
  const cancelInteraction = () => {
    const current = gesture.current;
    if (current && !props.readOnly) props.onChange(current.annotation.id, current.annotation);
    gesture.current = null; box.current = null; pan.current = null;
    setTemporaryBox(null); setPanning(false);setEditing(false);
  };
  useEffect(() => {
    setLoaded(current=>current?.src===props.src?current:undefined);setFailed(false);setDraft([]);setTemporaryBox(null);
    gesture.current=null;box.current=null;pan.current=null;setPanning(false);setEditing(false);
    fitMode.current=true;updateView({scale:1,offsetX:0,offsetY:0});
  }, [props.src]);
  useEffect(() => {
    const element = workspaceRef.current!;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      const next = {width:element.clientWidth || rect.width, height:element.clientHeight || rect.height};
      const previous = sizeRef.current;
      sizeRef.current = next;
      if (imageRef.current) updateView(fitMode.current ? fitViewport(imageRef.current, next) : resizedViewport(viewRef.current, previous, next));
    };
    measure();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : undefined;
    observer?.observe(element);window.addEventListener('resize', measure);
    const wheel = (event: WheelEvent) => {
      if (!imageRef.current || !event.deltaY || gesture.current || box.current || pan.current) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? sizeRef.current.height || 800 : 1;
      zoom(Math.exp(Math.max(-2, Math.min(2, -event.deltaY * unit * 0.0015))), localPoint(event));
    };
    element.addEventListener('wheel', wheel, {passive:false});
    return () => {observer?.disconnect();window.removeEventListener('resize',measure);element.removeEventListener('wheel',wheel);};
  }, []);
  useEffect(() => {if (image) reset(true);}, [image]);
  useEffect(() => {if (props.resetViewportKey) reset(false);}, [props.resetViewportKey]);
  useEffect(() => {if (props.mode !== 'polygon') setDraft([]);}, [props.mode]);
  useEffect(() => {
    const textInput = (target: EventTarget | null) => target instanceof HTMLElement && !!target.closest('input,textarea,select,[contenteditable="true"]');
    const down = (event: KeyboardEvent) => {
      if (textInput(event.target)) return;
      if (event.code === 'Space' || event.key === ' ') {
        space.current=true;setSpaceHeld(true);
        if (hovering.current || workspaceRef.current?.contains(document.activeElement)) event.preventDefault();
      }
      if ((space.current || pan.current) && (event.key === 'Delete' || event.key === 'Backspace')) {
        event.preventDefault();event.stopImmediatePropagation();
      }
    };
    const up = (event: KeyboardEvent) => {if (event.code === 'Space' || event.key === ' ') {space.current=false;setSpaceHeld(false);}};
    const blur = () => {space.current=false;setSpaceHeld(false);cancelInteraction();};
    window.addEventListener('keydown',down,true);window.addEventListener('keyup',up);window.addEventListener('blur',blur);
    return () => {window.removeEventListener('keydown',down,true);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);};
  }, [props.readOnly, props.onChange]);
  const begin = (event: ReactPointerEvent, a: DraftAnnotation, handle='move', vertex?: number) => {
    event.stopPropagation();
    if (space.current || pan.current) return;
    props.onSelect(a.id);
    if (!editable(a) || event.button!==0 || !imageRef.current) return;
    event.preventDefault();
    gesture.current={annotation:structuredClone(a), start:pointerPoint(event), handle, vertex, pointerId:event.pointerId};
    setEditing(true);
    workspaceRef.current?.setPointerCapture?.(event.pointerId);
  };
  function finishPolygon() {
    if (props.readOnly || space.current || pan.current) return;
    const points=dedupePolygonPoints(draft);
    if (points.length<3) {setDraft([]);return;}
    const selectedClass=classes.find(item=>item.id===props.classId);
    if (!selectedClass) {alert('Please select a class first.');return;}
    const xs=points.map(([x])=>x), ys=points.map(([,y])=>y);
    props.onAdd({class_id:selectedClass.id,class_name:selectedClass.name,annotation_type:'polygon',points,
      x:Math.min(...xs),y:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)});
    setDraft([]);props.onSelect(undefined);
  }
  useEffect(() => {
    const down=(event:KeyboardEvent)=>{
      if(props.mode!=='polygon'||space.current||pan.current||(event.target instanceof HTMLElement&&event.target.closest('input,textarea,select,[contenteditable="true"]')))return;
      if(event.key==='Escape'){setDraft([]);event.preventDefault();}
      if(event.key==='Enter'){finishPolygon();event.preventDefault();}
    };
    window.addEventListener('keydown',down);return()=>window.removeEventListener('keydown',down);
  }, [props.mode, props.readOnly, draft, props.classId, classes]);
  const boxAt=(start:Point,[x,y]:Point)=>({x:Math.min(x,start[0]),y:Math.min(y,start[1]),width:Math.abs(x-start[0]),height:Math.abs(y-start[1])});
  const finishBox=(event:ReactPointerEvent)=>{
    if(!box.current||!image)return;
    const finalBox=boxAt(box.current.start,pointerPoint(event));
    const selectedClass=classes.find(item=>item.id===props.classId);
    box.current=null;setTemporaryBox(null);
    if(!props.readOnly&&!space.current&&finalBox.width>2&&finalBox.height>2&&selectedClass)
      props.onAdd({class_id:selectedClass.id,class_name:selectedClass.name,annotation_type:'bbox',points:null,...finalBox});
  };
  const scale=view.scale, displayWidth=sizeRef.current.width || (image?.width??0)*scale;
  const busy=panning||editing||!!box.current;
  return <div className="canvas annotation-canvas">
    <div className="viewport-toolbar" role="toolbar" aria-label="Image zoom">
      <button aria-label="Zoom out" disabled={!image||busy} onClick={()=>zoom(1/1.25)}>−</button>
      <output aria-label="Zoom level">{(scale*100).toLocaleString('en-US',{maximumFractionDigits:scale<0.1?4:1})}%</output>
      <button aria-label="Zoom in" disabled={!image||busy} onClick={()=>zoom(1.25)}>+</button>
      <button disabled={!image||busy} onClick={()=>reset(false)}>Reset 100%</button>
      <button disabled={!image||busy} onClick={()=>reset(true)}>Fit to screen</button>
    </div>
    <div ref={workspaceRef} className={'annotation-viewport '+(panning?'is-panning':spaceHeld?'can-pan':props.mode==='select'?'is-select':'is-drawing')}
      role="region" aria-label="Annotation workspace" tabIndex={0}
      onPointerEnter={()=>{hovering.current=true;}} onPointerLeave={()=>{hovering.current=false;}}
      onPointerDownCapture={event=>{
        if(event.button!==0||!space.current||!image)return;
        event.preventDefault();event.stopPropagation();cancelInteraction();
        pan.current={start:localPoint(event),view:viewRef.current,pointerId:event.pointerId};fitMode.current=false;setPanning(true);
        event.currentTarget.focus({preventScroll:true});event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={event=>{
        if(!image)return;
        if(pan.current){const p=localPoint(event),g=pan.current;if(event.pointerId!==g.pointerId)return;updateView({...g.view,offsetX:g.view.offsetX+p[0]-g.start[0],offsetY:g.view.offsetY+p[1]-g.start[1]});return;}
        if(space.current||props.readOnly)return;
        const p=pointerPoint(event),g=gesture.current;
        if(g&&event.pointerId===g.pointerId)props.onChange(g.annotation.id,moveGeometry(g.annotation,p[0]-g.start[0],p[1]-g.start[1],image.width,image.height,g.handle,g.vertex));
        if(box.current&&event.pointerId===box.current.pointerId)setTemporaryBox(boxAt(box.current.start,p));
      }}
      onPointerUp={event=>{
        if(pan.current){if(event.pointerId!==pan.current.pointerId)return;pan.current=null;setPanning(false);}
        else{if(gesture.current&&event.pointerId!==gesture.current.pointerId)return;if(box.current&&event.pointerId!==box.current.pointerId)return;finishBox(event);gesture.current=null;setEditing(false);}
        if(event.currentTarget.hasPointerCapture?.(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={cancelInteraction} onLostPointerCapture={()=>{if(pan.current||gesture.current||box.current)cancelInteraction();}}>
      {!image&&<span className="canvas-loading">{failed?'Unable to load this image file.':'Loading image…'}</span>}
      <div className={'annotation-surface'+(!image?' is-loading':'')} style={{width:image?.width??1,height:image?.height??1,transform:'translate('+view.offsetX+'px, '+view.offsetY+'px) scale('+scale+')'}}>
        <ProtectedImage key={props.src} src={props.src} alt="Annotation target" draggable={false} onLoad={event=>{
          if(sourceRef.current!==props.src)return;
          const {naturalWidth:width,naturalHeight:height}=event.currentTarget;
          if(width>0&&height>0)setLoaded({src:props.src,width,height});else setFailed(true);
        }} onError={()=>setFailed(true)} onLoadFailure={()=>setFailed(true)}/>
        {image&&<svg viewBox={'0 0 '+image.width+' '+image.height} onPointerDown={event=>{
          if(props.readOnly||space.current||event.button!==0)return;
          const raw=screenToImage(localPoint(event),viewRef.current);
          if(raw[0]<0||raw[1]<0||raw[0]>image.width||raw[1]>image.height)return;
          if(props.mode==='select'){props.onSelect(undefined);return;}
          if(!classes.some(item=>item.id===props.classId)){alert('Please select a class first.');return;}
          event.preventDefault();
          const point=pointerPoint(event);
          if(props.mode==='draw'){box.current={start:point,pointerId:event.pointerId};setTemporaryBox(boxAt(point,point));workspaceRef.current?.setPointerCapture?.(event.pointerId);}
          else if(props.mode==='polygon')setDraft(current=>[...current,point]);
        }} onDoubleClick={event=>{if(props.mode==='polygon'&&!space.current&&!pan.current){event.preventDefault();finishPolygon();}}}>
    {annotations.map((annotation, index) => {
      const id = numberOr(annotation.id, -index - 1), classIndex = classes.findIndex((item) => item.id === annotation.class_id), color = colors[classIndex >= 0 ? classIndex % colors.length : 0];
      const points = validPoints(annotation.points), polygon = annotation.annotation_type === "polygon" && points.length >= 3, x = numberOr(annotation.x), y = numberOr(annotation.y), width = Math.max(0, numberOr(annotation.width)), height = Math.max(0, numberOr(annotation.height));
      const select = (event: ReactMouseEvent<SVGElement>) => { event.stopPropagation(); if(!space.current&&!pan.current)props.onSelect(id); };
      const fullLabel = annotationLabel(annotation), maxChars = Math.max(8, Math.min(44, Math.floor(displayWidth / 8)));
      const label = Array.from(fullLabel).length > maxChars ? Array.from(fullLabel).slice(0, maxChars - 1).join("") + "…" : fullLabel;
      const labelWidth = Math.min(image.width, (Array.from(label).length * 8 + 10) / scale);
      const labelX = Math.max(0, Math.min(x, image.width - labelWidth));
      const labelY = Math.max(0, Math.min(image.height - 18 / scale, Math.max(0, y - 22 / scale)));
      return <g key={`annotation-${id}`} data-annotation-id={id} onMouseDown={select} onPointerDown={event=>begin(event,annotation)}><title>{fullLabel}</title>{polygon ? <polygon points={pointsAttribute(points)} fill={color} fillOpacity="0.18" stroke={color} strokeWidth={props.selected === id ? 3 / scale : 2 / scale}/> : <rect x={x} y={y} width={width} height={height} fill="transparent" stroke={color} strokeWidth={props.selected === id ? 3 / scale : 2 / scale}/>}<g pointerEvents="none"><rect x={labelX} y={labelY} width={labelWidth} height={20 / scale} rx={3 / scale} fill="#0f172a" fillOpacity="0.9"/><text x={labelX + 4 / scale} y={labelY + 14 / scale} fill={color} fontSize={13 / scale}>{label}</text></g>{props.selected===id&&editable(annotation)&&(polygon?points.map(([px,py],vertex)=><circle key={vertex} aria-label={`Vertex ${vertex+1}`} cx={px} cy={py} r={5/scale} fill="white" stroke={color} strokeWidth={2/scale} style={{cursor:'crosshair'}} onPointerDown={event=>begin(event,annotation,'vertex',vertex)}/>):[['nw',x,y],['n',x+width/2,y],['ne',x+width,y],['e',x+width,y+height/2],['se',x+width,y+height],['s',x+width/2,y+height],['sw',x,y+height],['w',x,y+height/2]].map(([handle,hx,hy])=><rect key={handle} aria-label={`Resize ${handle}`} x={Number(hx)-4/scale} y={Number(hy)-4/scale} width={8/scale} height={8/scale} fill="white" stroke={color} strokeWidth={1.5/scale} style={{cursor:`${handle}-resize`}} onPointerDown={event=>begin(event,annotation,String(handle))}/>))}</g>;
    })}
    {predictions.filter((prediction) => prediction.status === "PENDING").map((prediction, index) => {
      const id = numberOr(prediction.id, -100000 - index), points = validPoints(prediction.points), polygon = prediction.prediction_type === "polygon" && points.length >= 3, x = numberOr(prediction.x), y = numberOr(prediction.y), stroke = props.selectedPrediction === id ? "#facc15" : "#ec4899", confidence = numberOr(prediction.confidence);
      return <g key={`prediction-${id}`} onPointerDown={event=>{event.stopPropagation();if(!space.current&&!pan.current)props.onSelectPrediction?.(id);}} onMouseDown={event=>{event.stopPropagation();if(!space.current&&!pan.current)props.onSelectPrediction?.(id);}}>{polygon ? <polygon points={pointsAttribute(points)} fill="#ec4899" fillOpacity="0.1" stroke={stroke} strokeWidth={2 / scale} strokeDasharray={`${8 / scale} ${5 / scale}`}/> : <rect x={x} y={y} width={Math.max(0, numberOr(prediction.width))} height={Math.max(0, numberOr(prediction.height))} fill="transparent" stroke={stroke} strokeWidth={2 / scale} strokeDasharray={`${8 / scale} ${5 / scale}`}/>}<text x={x} y={Math.max(0, y - 6 / scale)} fill="#ec4899" fontSize={14 / scale}>{`${typeof prediction.model_class_name === "string" ? prediction.model_class_name : "Prediction"} ${(confidence * 100).toFixed(0)}%`}</text></g>;
    })}
    {temporaryBox && <rect {...temporaryBox} fill="transparent" stroke="#eab308" strokeWidth={2 / scale} strokeDasharray={`${6 / scale} ${4 / scale}`}/>} {draft.length > 0 && <><polyline points={pointsAttribute(draft)} fill="none" stroke="#eab308" strokeWidth={2 / scale} strokeDasharray={`${6 / scale} ${4 / scale}`}/>{draft.map(([x, y], index) => <circle key={`draft-${index}`} cx={x} cy={y} r={4 / scale} fill="#eab308"/>)}</>}
        </svg>}
      </div>
    </div>
    <small>{image?image.width+' × '+image.height+' · ':''}Wheel to zoom · Space + drag to pan{props.mode==='polygon'&&' · click vertices, double-click or Finish to complete'}</small>
    {!props.readOnly&&props.mode==='polygon'&&<span className="canvas-actions"><button onClick={finishPolygon}>Finish polygon</button><button onClick={()=>setDraft([])}>Cancel</button></span>}
  </div>;
}
