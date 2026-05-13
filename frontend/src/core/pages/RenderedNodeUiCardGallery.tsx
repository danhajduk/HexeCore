import { ArrowLeft, Boxes } from "lucide-react";
import { Link } from "react-router-dom";

import { NodeUiCard, pilotNodeUiCardResponses, pilotNodeUiManifest } from "../rendered-node-ui";
import "./rendered-node-ui-card-gallery.css";

export default function RenderedNodeUiCardGallery() {
  const surfaces = pilotNodeUiManifest.pages
    .flatMap((page) => page.surfaces)
    .filter((surface) => ["health_strip", "warning_banner"].includes(surface.kind));

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
              <p>Rendered page card previews.</p>
            </div>
          </div>
        </div>
        <div className="rendered-card-gallery-summary">
          <span>{surfaces.length} cards</span>
          <span>{pilotNodeUiManifest.pages.length} pages</span>
        </div>
      </header>

      <div className="rendered-card-gallery-grid">
        {surfaces.map((surface) => {
          const data = pilotNodeUiCardResponses[surface.kind];
          if (!data) return null;
          return (
            <section key={surface.id} className="rendered-card-gallery-item">
              <NodeUiCard surface={surface} data={data} onAction={() => undefined} />
            </section>
          );
        })}
      </div>
    </section>
  );
}
