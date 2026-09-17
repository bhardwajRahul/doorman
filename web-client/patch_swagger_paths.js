const fs = require('fs');
const file = 'src/app/apis/import-swagger/page.tsx';
let code = fs.readFileSync(file, 'utf8');

// 1. Add client_uri to ParsedEndpoint interface
code = code.replace(
  "auth_required: boolean;",
  "auth_required: boolean;\n  client_uri: string;"
);

// 2. Update ParsedEndpoint push
code = code.replace(
  "upstream_server: '',",
  "upstream_server: '',\n                client_uri: path,"
);

// 3. Add bulk prefix state
code = code.replace(
  "const [bulkRateLimit, setBulkRateLimit] = useState(100)",
  "const [bulkRateLimit, setBulkRateLimit] = useState(100)\n  const [bulkPrefix, setBulkPrefix] = useState('')"
);

// 4. Update applyBulkSettings
code = code.replace(
  "rate_limit: bulkRateLimit",
  "rate_limit: bulkRateLimit,\n        client_uri: bulkPrefix ? (bulkPrefix + ep.path).replace(/\\/\\//g, '/') : ep.client_uri"
);

// 5. Update epPayload
code = code.replace(
  "endpoint_uri: ep.path,",
  "endpoint_uri: ep.path,\n          client_uri: ep.client_uri !== ep.path ? ep.client_uri : undefined,"
);

// 6. Add bulk prefix input to Bulk Settings UI
const bulkServerRegex = /<div className="col-span-2">[\s\S]*?<label[\s\S]*?Upstream Server[\s\S]*?<\/div>/;
const newBulkSettings = `<div className="col-span-1">
                <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Upstream Server</label>
                <input type="text" placeholder="http://api.internal" value={bulkServer} onChange={e => setBulkServer(e.target.value)} className="w-full border-2 border-gray-900 p-2" />
              </div>
              <div className="col-span-1">
                <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Path Prefix</label>
                <input type="text" placeholder="/api/v1" value={bulkPrefix} onChange={e => setBulkPrefix(e.target.value)} className="w-full border-2 border-gray-900 p-2" />
              </div>`;
code = code.replace(bulkServerRegex, newBulkSettings);

// 7. Update table headers
const tableHeaders = `<th className="p-3 w-10"></th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Method</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Internal Path</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Custom Public Path</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Upstream</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Config</th>`;
code = code.replace(/<th className="p-3 w-10"><\/th>[\s\S]*?<th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Config<\/th>/, tableHeaders);

// 8. Update table row
const oldRow = /<td className="p-3 font-mono text-sm align-middle truncate max-w-\[200px\]" title=\{ep.path\}>\{ep.path\}<\/td>/;
const newRow = `<td className="p-3 font-mono text-sm align-middle truncate max-w-[200px]" title={ep.path}>{ep.path}</td>
                      <td className="p-3 align-middle">
                        <input type="text" value={ep.client_uri} onChange={e => {
                          const val = e.target.value;
                          setEndpoints(prev => prev.map(p => p.id === ep.id ? {...p, client_uri: val} : p))
                        }} className="w-full p-1 border-2 border-gray-900 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#38bdf8]" />
                      </td>`;
code = code.replace(oldRow, newRow);

fs.writeFileSync(file, code);
