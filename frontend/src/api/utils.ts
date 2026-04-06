/** Parse full_output which may be a JSON string from the DB or an object */
export function parseOutput(data: any): any {
  const fo = data?.full_output;
  if (!fo) return {};
  if (typeof fo === 'string') {
    try { return JSON.parse(fo); } catch { return {}; }
  }
  return fo;
}
