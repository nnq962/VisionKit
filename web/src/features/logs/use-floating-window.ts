"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";
import { resizeWindow, WINDOW_MARGIN } from "./window-geometry";
import type { ResizeDirection, WindowBounds } from "./window-geometry";

type Position = { x: number; y: number };
const MARGIN = WINDOW_MARGIN;

function constrain(position: Position, element: HTMLElement): Position {
  return {
    x: Math.max(MARGIN, Math.min(position.x, window.innerWidth - element.offsetWidth - MARGIN)),
    y: Math.max(MARGIN, Math.min(position.y, window.innerHeight - element.offsetHeight - MARGIN)),
  };
}

export function useFloatingWindow(open: boolean) {
  const windowRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const restoreSize = useRef<typeof size>(null);
  const restorePosition = useRef<Position | null>(null);
  const resize = useRef<{ pointerId: number; x: number; y: number; direction: ResizeDirection; initial: WindowBounds } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [windowElement, setWindowElement] = useState<HTMLDivElement | null>(null);
  const attachWindow = useCallback((element: HTMLDivElement | null) => {
    windowRef.current = element;
    setWindowElement(element);
    if (!element) {
      drag.current = null;
      resize.current = null;
      setDragging(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !windowElement) return;
    const element = windowElement;
    // Khi đổi kích thước cửa sổ/panel, giữ cả phần header trong vùng nhìn thấy.
    const reposition = () => {
      setSize((current) => {
        if (!current) return current;
        const width = Math.min(current.width, window.innerWidth - MARGIN * 2);
        const height = Math.min(current.height, window.innerHeight - MARGIN * 2);
        return width === current.width && height === current.height ? current : { width, height };
      });
      setPosition((current) => {
        if (!current) return current;
        const next = constrain(current, element);
        return next.x === current.x && next.y === current.y ? current : next;
      });
    };
    const observer = new ResizeObserver(reposition);
    observer.observe(element);
    window.addEventListener("resize", reposition);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", reposition);
      drag.current = null;
      resize.current = null;
    };
  }, [open, windowElement]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || event.button !== 0 || !windowRef.current) return;
    if ((event.target as HTMLElement).closest("button, a, input, select, textarea")) return;
    const rect = windowRef.current.getBoundingClientRect();
    drag.current = { pointerId: event.pointerId, offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    event.preventDefault();
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || drag.current.pointerId !== event.pointerId || !windowRef.current) return;
    setPosition(constrain({ x: event.clientX - drag.current.offsetX, y: event.clientY - drag.current.offsetY }, windowRef.current));
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget || !windowRef.current) return;
    if (event.key === "Home") {
      event.preventDefault();
      setPosition(null);
      return;
    }
    const direction: Record<string, Position> = {
      ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 },
      ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 },
    };
    const offset = direction[event.key];
    if (!offset) return;
    event.preventDefault();
    const rect = windowRef.current.getBoundingClientRect();
    const step = event.shiftKey ? 40 : 10;
    setPosition(constrain({ x: rect.left + offset.x * step, y: rect.top + offset.y * step }, windowRef.current));
  }

  function toggleExpanded() {
    if (expanded) {
      setSize(restoreSize.current);
      setPosition(restorePosition.current);
    } else {
      restoreSize.current = size;
      restorePosition.current = position;
      setSize({ width: Math.min(900, window.innerWidth - MARGIN * 2), height: Math.min(680, window.innerHeight - MARGIN * 2) });
    }
    setExpanded(!expanded);
  }

  function applyResize(direction: ResizeDirection, dx: number, dy: number, initial: WindowBounds) {
    const next = resizeWindow(initial, direction, dx, dy, { width: window.innerWidth, height: window.innerHeight });
    setPosition({ x: next.x, y: next.y });
    setSize({ width: next.width, height: next.height });
    setExpanded(false);
  }

  function getResizeHandleProps(direction: ResizeDirection) {
    function finish(event: PointerEvent<HTMLDivElement>) {
      if (resize.current?.pointerId !== event.pointerId) return;
      resize.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    }
    return {
      onPointerDown(event: PointerEvent<HTMLDivElement>) {
        if (!event.isPrimary || event.button !== 0 || !windowRef.current) return;
        const rect = windowRef.current.getBoundingClientRect();
        resize.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, direction,
          initial: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
        event.currentTarget.setPointerCapture(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
      },
      onPointerMove(event: PointerEvent<HTMLDivElement>) {
        const current = resize.current;
        if (!current || current.pointerId !== event.pointerId) return;
        applyResize(current.direction, event.clientX - current.x, event.clientY - current.y, current.initial);
      },
      onPointerUp: finish, onPointerCancel: finish, onLostPointerCapture: finish,
      onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
        const offsets: Record<string, Position> = { ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 }, ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 } };
        const offset = offsets[event.key];
        if (!offset || !windowRef.current) return;
        event.preventDefault();
        const rect = windowRef.current.getBoundingClientRect();
        const step = event.shiftKey ? 40 : 10;
        applyResize(direction, offset.x * step, offset.y * step, { x: rect.x, y: rect.y, width: rect.width, height: rect.height });
      },
    };
  }

  const style: CSSProperties = {
    ...(position ? { left: position.x, top: position.y, right: "auto", bottom: "auto" } : {}),
    ...(size ? { width: size.width, height: size.height } : {}),
  };

  return {
    windowRef: attachWindow,
    style, expanded, toggleExpanded, getResizeHandleProps,
    headerProps: {
      onPointerDown, onPointerMove, onPointerUp: endDrag,
      onPointerCancel: endDrag, onLostPointerCapture: endDrag, onKeyDown,
      "data-dragging": dragging,
    },
  };
}
