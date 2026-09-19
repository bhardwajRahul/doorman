const fs = require('fs');
const file = 'src/app/apis/import-swagger/page.tsx';
let code = fs.readFileSync(file, 'utf8');

// 1. Remove Section 3 (Bulk Settings) and merge into Section 4 (which becomes Section 3)
const section3Regex = /<div className="bg-white border-2 border-gray-900 shadow-\[4px_4px_0px_0px_rgba\(15,23,42,1\)\] p-6">[\s\S]*?<h2 className="text-lg font-bold text-gray-900 mb-4 uppercase tracking-wider">3\. Bulk Endpoint Settings<\/h2>[\s\S]*?Apply to Selected[\s\S]*?<\/button>[\s\S]*?<\/div>[\s\S]*?<div className="bg-white border-2 border-gray-900 shadow-\[4px_4px_0px_0px_rgba\(15,23,42,1\)\] p-0 overflow-hidden">/m;

const newSection3Header = `<div className="bg-white border-2 border-gray-900 shadow-[4px_4px_0px_0px_rgba(15,23,42,1)] p-0 overflow-hidden">
            <div className="p-4 border-b-2 border-gray-900 bg-gray-50">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-bold text-gray-900 uppercase tracking-wider">3. Review Endpoints ({endpoints.filter(e=>e.selected).length} selected)</h2>
                <div className="space-x-4">
                  <button onClick={() => toggleAll(true)} className="text-sm font-bold text-gray-600 hover:text-gray-900 uppercase transition-colors">Select All</button>
                  <button onClick={() => toggleAll(false)} className="text-sm font-bold text-gray-600 hover:text-gray-900 uppercase transition-colors">Deselect All</button>
                </div>
              </div>
              
              <div className="bg-gray-200 border-2 border-gray-900 p-3 flex flex-wrap gap-4 items-end">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Servers (comma separated)</label>
                  <input type="text" placeholder="http://api1, http://api2" value={bulkServer} onChange={e => setBulkServer(e.target.value)} className="w-full border-2 border-gray-900 p-1.5 text-sm" />
                </div>
                <div className="w-48">
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Path Prefix</label>
                  <input type="text" placeholder="/api/v1" value={bulkPrefix} onChange={e => setBulkPrefix(e.target.value)} className="w-full border-2 border-gray-900 p-1.5 text-sm" />
                </div>
                <div className="w-24">
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Rate Limit</label>
                  <input type="number" value={bulkRateLimit} onChange={e => setBulkRateLimit(parseInt(e.target.value) || 0)} className="w-full border-2 border-gray-900 p-1.5 text-sm" />
                </div>
                <div className="flex items-center gap-2 pb-2">
                  <input type="checkbox" checked={bulkAuth} onChange={e => setBulkAuth(e.target.checked)} className="w-4 h-4 cursor-pointer border-2 border-gray-900" />
                  <span className="text-sm font-bold uppercase text-gray-700">Auth</span>
                </div>
                <button onClick={applyBulkSettings} className="px-4 py-1.5 bg-gray-900 text-white font-bold uppercase text-xs hover:bg-gray-800 transition-colors">
                  Bulk Apply
                </button>
              </div>
            </div>`;

code = code.replace(section3Regex, newSection3Header);

// 2. Change Table Headers
const oldHeadersRegex = /<th className="p-3 w-10"><\/th>[\s\S]*?<th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Config<\/th>/;
const newHeaders = `<th className="p-3 w-10"></th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Method</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Backend Path</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">New Path (optional)</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Servers</th>
                    <th className="p-3 text-xs font-bold uppercase text-gray-600 whitespace-nowrap">Config</th>`;
code = code.replace(oldHeadersRegex, newHeaders);

// 3. Update the Servers input in the table row to say "Inherit from API" or support commas
const oldUpstreamInputRegex = /<input type="text" value=\{ep.upstream_server\} onChange=\{e => \{[\s\S]*?\}\} placeholder="Inherit from API" className="w-full p-1 border-2 border-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-\[#a3e635\]" \/>/m;
const newUpstreamInput = `<input type="text" value={ep.upstream_server} onChange={e => {
                          const val = e.target.value;
                          setEndpoints(prev => prev.map(p => p.id === ep.id ? {...p, upstream_server: val} : p))
                        }} placeholder="Inherit from API (comma separate for multiple)" className="w-full p-1 border-2 border-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-[#38bdf8]" />`;
code = code.replace(oldUpstreamInputRegex, newUpstreamInput);

// 4. Update publish endpoints loop to split servers by comma
const epPayloadRegex = /endpoint_servers: ep\.upstream_server \? \[ep\.upstream_server\] : \[\]/g;
const newEpPayload = `endpoint_servers: ep.upstream_server ? ep.upstream_server.split(',').map(s=>s.trim()).filter(Boolean) : []`;
code = code.replace(epPayloadRegex, newEpPayload);

// 5. Update create API payload to split servers by comma
const apiPayloadRegex = /api_servers: bulkServer \? \[bulkServer\] : \[\]/g;
const newApiPayload = `api_servers: bulkServer ? bulkServer.split(',').map(s=>s.trim()).filter(Boolean) : []`;
code = code.replace(apiPayloadRegex, newApiPayload);

fs.writeFileSync(file, code);
