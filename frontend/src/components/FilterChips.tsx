interface FilterChipsProps {
  options: string[];
  active: string;
  onChange: (value: string) => void;
}

export function FilterChips({ options, active, onChange }: FilterChipsProps) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {options.map(option => (
        <button
          key={option}
          className={`filter-chip${active === option ? ' active' : ''}`}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export default FilterChips;
