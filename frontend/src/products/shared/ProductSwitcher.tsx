import { useI18n } from '../../i18n';
import { LanguageSelect } from '../../i18n/LanguageSelect';
import { CodeOutlined, ReadOutlined, UnorderedListOutlined } from '@ant-design/icons';

export type ProductKey = 'work' | 'knowledge' | 'code';

const products: Array<{ key: ProductKey; name: string; icon: React.ReactNode; href: string }> = [
  { key: 'work', name: 'Work', icon: <UnorderedListOutlined />, href: '/work' },
  { key: 'knowledge', name: 'Knowledge', icon: <ReadOutlined />, href: '/knowledge' },
  { key: 'code', name: 'Code', icon: <CodeOutlined />, href: '/code' },
];

const standaloneProduct = ['work', 'knowledge', 'code'].includes(import.meta.env.MODE)
  ? import.meta.env.MODE as ProductKey
  : null;

export function ProductSwitcher({ active, compact = false, showLanguage = true }: { active: ProductKey; compact?: boolean; showLanguage?: boolean }) {
  const { t } = useI18n();
  const visibleProducts = standaloneProduct ? products.filter((product) => product.key === standaloneProduct) : products;
  return (
    <><nav className={`product-switcher${compact ? ' product-switcher-compact' : ''}`} aria-label={t('Ordivant 產品')}>
      {visibleProducts.map((product) => (
        <a key={product.key} href={product.href} className={`product-switch-link${active === product.key ? ' product-switch-active' : ''}`} aria-current={active === product.key ? 'page' : undefined}>
          <span>{product.icon}</span><span>{product.name}</span>
        </a>
      ))}
    </nav>{showLanguage && <LanguageSelect />}</>
  );
}
