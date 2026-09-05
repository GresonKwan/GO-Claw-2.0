import {
  EyeOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useTranslation } from "react-i18next";
import type { DeliverableItem } from "@/api/modules/deliverables";
import { deliverablesApi } from "@/api/modules/deliverables";
import styles from "./index.module.less";

const CARD_WIDTH = 180;
const CARD_GAP = 10;
const CARD_STRIDE = CARD_WIDTH + CARD_GAP;
const OVERSCAN_CARDS = 1;

function MediaCard({
  item,
  onPreview,
  onReveal,
}: {
  item: DeliverableItem;
  onPreview: (item: DeliverableItem, target: HTMLButtonElement) => void;
  onReveal: (item: DeliverableItem) => void;
}) {
  const { t } = useTranslation();
  const [thumbnail, setThumbnail] = useState("");
  useEffect(() => {
    let active = true;
    if (item.previewKind !== "image") return () => undefined;
    deliverablesApi
      .mediaTicket(item.id)
      .then(({ ticket }) => {
        if (active)
          setThumbnail(deliverablesApi.mediaUrl(item.id, ticket, "thumbnail"));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [item.id, item.previewKind]);

  return (
    <article className={styles.mediaCard} tabIndex={0} aria-label={item.name}>
      <div className={styles.mediaVisual}>
        {thumbnail ? (
          <img src={thumbnail} alt="" loading="lazy" />
        ) : (
          <span className={styles.mediaPlaceholder}>
            <PlayCircleOutlined />
          </span>
        )}
        <div className={styles.mediaActions}>
          <button
            type="button"
            aria-label={t("deliverables.previewNamed", { name: item.name })}
            disabled={!item.previewAllowed || !item.exists}
            onClick={(event) => onPreview(item, event.currentTarget)}
          >
            <EyeOutlined />
          </button>
          <button
            type="button"
            aria-label={t("deliverables.revealNamed", { name: item.name })}
            disabled={!item.exists}
            onClick={() => onReveal(item)}
          >
            <FolderOpenOutlined />
          </button>
        </div>
      </div>
      <div className={styles.mediaName} title={item.name}>
        {item.name}
      </div>
    </article>
  );
}

export default function MediaDeliverablesRail({
  items,
  onPreview,
  onReveal,
}: {
  items: DeliverableItem[];
  onPreview: (item: DeliverableItem, target: HTMLButtonElement) => void;
  onReveal: (item: DeliverableItem) => void;
}) {
  const { t } = useTranslation();
  const railRef = useRef<HTMLDivElement>(null);
  const thumbRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<number>();
  const [visible, setVisible] = useState(false);
  const [windowRange, setWindowRange] = useState(() => ({
    start: 0,
    end: Math.min(items.length, 2),
  }));

  const sync = useCallback(() => {
    const rail = railRef.current;
    const thumb = thumbRef.current;
    if (!rail || !thumb) return;
    const ratio = rail.clientWidth / Math.max(rail.scrollWidth, 1);
    const width = Math.max(36, rail.clientWidth * ratio);
    const travel = rail.clientWidth - width;
    const progress =
      rail.scrollLeft / Math.max(rail.scrollWidth - rail.clientWidth, 1);
    thumb.style.width = `${width}px`;
    thumb.style.transform = `translateX(${travel * progress}px)`;
    thumb.hidden = ratio >= 1;

    const firstVisible = Math.floor(rail.scrollLeft / CARD_STRIDE);
    const visibleCards = Math.max(1, Math.ceil(rail.clientWidth / CARD_STRIDE));
    const start = Math.max(0, firstVisible - OVERSCAN_CARDS);
    const end = Math.min(
      items.length,
      firstVisible + visibleCards + OVERSCAN_CARDS,
    );
    setWindowRange((current) =>
      current.start === start && current.end === end ? current : { start, end },
    );
  }, [items.length]);

  useLayoutEffect(() => {
    setWindowRange((current) => ({
      start: Math.min(current.start, Math.max(items.length - 1, 0)),
      end: Math.min(
        items.length,
        Math.max(current.end, Math.min(items.length, 2)),
      ),
    }));
    sync();
    const observer = new ResizeObserver(sync);
    if (railRef.current) observer.observe(railRef.current);
    return () => {
      observer.disconnect();
      window.clearTimeout(hideTimer.current);
    };
  }, [items.length, sync]);

  const showDuringScroll = () => {
    sync();
    setVisible(true);
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => {
      hideTimer.current = undefined;
      setVisible(false);
    }, 800);
  };

  const beginThumbDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const rail = railRef.current;
    const thumb = thumbRef.current;
    if (!rail || !thumb) return;
    event.preventDefault();
    setVisible(true);
    const startX = event.clientX;
    const startScroll = rail.scrollLeft;
    const thumbWidth = thumb.getBoundingClientRect().width;
    const trackTravel = Math.max(rail.clientWidth - thumbWidth, 1);
    const scrollTravel = Math.max(rail.scrollWidth - rail.clientWidth, 0);
    const move = (next: PointerEvent) => {
      rail.scrollLeft =
        startScroll + ((next.clientX - startX) / trackTravel) * scrollTravel;
    };
    const finish = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      showDuringScroll();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish, { once: true });
  };

  return (
    <div
      className={`${styles.railShell} ${visible ? styles.scrolling : ""}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => !hideTimer.current && setVisible(false)}
      onFocusCapture={() => setVisible(true)}
      onBlurCapture={() => setVisible(false)}
    >
      <div
        ref={railRef}
        className={styles.mediaRail}
        role="region"
        tabIndex={0}
        aria-label={t("deliverables.mediaRegion")}
        onScroll={showDuringScroll}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            railRef.current?.scrollBy({
              left: event.key === "ArrowRight" ? 196 : -196,
              behavior: "smooth",
            });
            event.preventDefault();
          }
        }}
        onWheel={(event) => {
          if (event.shiftKey && railRef.current) {
            railRef.current.scrollLeft += event.deltaY;
            event.preventDefault();
          }
        }}
      >
        {windowRange.start > 0 && (
          <div
            className={styles.mediaSpacer}
            style={{ flexBasis: windowRange.start * CARD_STRIDE - CARD_GAP }}
            aria-hidden="true"
          />
        )}
        {items.slice(windowRange.start, windowRange.end).map((item) => (
          <MediaCard
            key={item.id}
            item={item}
            onPreview={onPreview}
            onReveal={onReveal}
          />
        ))}
        {windowRange.end < items.length && (
          <div
            className={styles.mediaSpacer}
            style={{
              flexBasis:
                (items.length - windowRange.end) * CARD_STRIDE - CARD_GAP,
            }}
            aria-hidden="true"
          />
        )}
      </div>
      <div
        className={styles.scrollOverlay}
        data-testid="deliverables-scroll-overlay"
        aria-hidden="true"
        style={{ position: "absolute" }}
      >
        <div
          ref={thumbRef}
          className={styles.scrollThumb}
          onPointerDown={beginThumbDrag}
        />
      </div>
    </div>
  );
}
