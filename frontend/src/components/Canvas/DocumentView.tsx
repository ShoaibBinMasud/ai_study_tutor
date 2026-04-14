import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Props {
  sectionTitle: string;
  content: string;
}

export default function DocumentView({ sectionTitle, content }: Props) {
  return (
    <div className="h-full flex flex-col bg-[#F9FAFB] overflow-hidden">
      {/* Search / Section Info */}
      <div className="px-6 py-3 border-b bg-white border-gray-100 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[10px] bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
            Current Module
          </span>
          <span className="text-xs font-bold text-gray-900 truncate">
            {sectionTitle || 'Tutor Notes'}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-10 scrollbar-thin">
        <div className="max-w-xl mx-auto canvas-paper bg-white p-10 rounded-2xl shadow-sm border border-gray-100 min-h-full">
          <h1 className="text-2xl font-bold text-gray-900 mb-6 border-b border-gray-50 pb-4">
            {sectionTitle || 'Comprehensive Summary'}
          </h1>
          <article className="prose prose-indigo prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkMath, remarkGfm]}
              rehypePlugins={[rehypeKatex]}
            >
              {content || 'Wait for the tutor to push detailed notes here!'}
            </ReactMarkdown>
          </article>
        </div>
      </div>
    </div>
  );
}
