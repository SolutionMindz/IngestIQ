declare module 'react-markdown' {
  import type { ComponentType } from 'react';
  interface ReactMarkdownProps {
    children: string;
    className?: string;
  }
  const ReactMarkdown: ComponentType<ReactMarkdownProps>;
  export default ReactMarkdown;
}
