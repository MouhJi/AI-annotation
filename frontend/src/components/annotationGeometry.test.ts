import {it,expect} from 'vitest';
import {moveGeometry} from './annotationGeometry';
import type {DraftAnnotation} from '../types';
const a:DraftAnnotation={id:123,class_id:1,class_name:'Car',annotation_type:'bbox',x:10,y:10,width:20,height:20};
it('moves and bounds the original box without changing identity or attribution',()=>{expect(moveGeometry(a,500,-30,100,80)).toEqual({x:80,y:0});expect(a.id).toBe(123);expect(a.x).toBe(10)});
it('resizes all eight handles without flipping coordinates',()=>{for(const handle of ['n','e','s','w','nw','ne','se','sw']){const change=moveGeometry(a,100,100,100,80,handle);expect(change.width).toBeGreaterThan(0);expect(change.height).toBeGreaterThan(0)}expect(moveGeometry(a,-5,-3,100,80,'nw')).toEqual({x:5,y:7,width:25,height:23})});
it('moves one polygon vertex and recomputes bbox',()=>{const p={...a,annotation_type:'polygon' as const,points:[[10,10],[30,10],[30,30],[10,30]] as [number,number][]};const change=moveGeometry(p,-5,-7,100,80,'vertex',0);expect(change.points?.[0]).toEqual([5,3]);expect(change.x).toBe(5);expect(change.y).toBe(3);expect(p.points[0]).toEqual([10,10])});
