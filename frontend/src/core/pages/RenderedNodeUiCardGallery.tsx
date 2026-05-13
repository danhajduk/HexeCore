import { useState } from "react";
import { ArrowLeft, Boxes, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import {
  NodeUiCard,
  pilotNodeUiCardResponses,
  pilotNodeUiManifest,
  type NodeUiActionState,
  type NodeUiSurface,
} from "../rendered-node-ui";
import "./rendered-node-ui-card-gallery.css";

type ActionNotice = {
  surfaceTitle: string;
  actionLabel: string;
};

export default function RenderedNodeUiCardGallery() {
  const [lastAction, setLastAction] = useState<ActionNotice | null>(null);
  const surfaces = pilotNodeUiManifest.pages.flatMap((page) => page.surfaces);

  function handleAction(action: NodeUiActionState, surface: NodeUiSurface) {
    setLastAction({
      surfaceTitle: surface.title,
      actionLabel: action.label || action.id,
    });
  }

  return (
    <section className="rendered-card-gallery">
      <header className="rendered-card-gallery-head">
        <div className="rendered-card-gallery-title">
          <Link to="/" className="rendered-card-gallery-back">
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Home</span>
          </Link>
          <div className="rendered-card-gallery-title-main">
            <div className="rendered-card-gallery-icon" aria-hidden="true">
              <Boxes size={22} />
            </div>
            <div>
              <div className="rendered-card-gallery-eyebrow">Rendered node UI helper</div>
              <h1>Card gallery</h1>
              <p>Fixture previews for every supported Core-rendered node card.</p>
            </div>
          </div>
        </div>
        <div className="rendered-card-gallery-summary">
          <span>{surfaces.length} cards</span>
          <span>{pilotNodeUiManifest.pages.length} pages</span>
        </div>
      </header>

      {lastAction ? (
        <div className="rendered-card-gallery-notice">
          <CheckCircle2 size={16} aria-hidden="true" />
          <span>
            Preview action: {lastAction.actionLabel} on {lastAction.surfaceTitle}
          </span>
        </div>
      ) : null}

      <div className="rendered-card-gallery-grid">
        {surfaces.map((surface) => {
          const data = pilotNodeUiCardResponses[surface.kind];
          if (!data) return null;
          return (
            <section key={surface.id} className="rendered-card-gallery-item">
              <div className="rendered-card-gallery-item-head">
                <span>{surface.kind}</span>
                <strong>{surface.title}</strong>
              </div>
              <NodeUiCard surface={surface} data={data} onAction={handleAction} />
            </section>
          );
        })}
      </div>
    </section>
  );
}
