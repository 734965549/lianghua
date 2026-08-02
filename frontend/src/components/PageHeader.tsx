import type { ReactNode } from "react";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  meta?: ReactNode;
};

export default function PageHeader({
  eyebrow = "LIANGHUA WORKSTATION",
  title,
  description,
  actions,
  meta,
}: Props) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        <div className="page-eyebrow">{eyebrow}</div>
        <div className="page-title-row">
          <h1>{title}</h1>
          {meta}
        </div>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}
