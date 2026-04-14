interface DiagramProps {
  html: string;
}

export default function Diagram({ html }: DiagramProps) {
  return (
    <iframe
      className="diagram-iframe"
      srcDoc={html}
      sandbox="allow-scripts"
      title="STEM diagram"
      scrolling="no"
    />
  );
}
