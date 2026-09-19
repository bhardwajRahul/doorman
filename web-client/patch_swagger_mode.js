const fs = require('fs');
const file = 'src/app/apis/import-swagger/page.tsx';
let code = fs.readFileSync(file, 'utf8');

// 1. Add useEffect to imports
code = code.replace(
  "import React, { useState } from 'react'",
  "import React, { useState, useEffect } from 'react'"
);

// 2. Add getJson to imports
code = code.replace(
  "import { postJson } from '@/utils/api'",
  "import { postJson, getJson } from '@/utils/api'"
);

// 3. Add states
const stateInjection = `const [apiName, setApiName] = useState('')
  const [apiVersion, setApiVersion] = useState('v1')
  
  const [apiTargetMode, setApiTargetMode] = useState<'new' | 'existing'>('new')
  const [existingApis, setExistingApis] = useState<{api_name: string, api_version: string}[]>([])
  
  useEffect(() => {
    const fetchApis = async () => {
      try {
        const data = await getJson<any>(\`\${SERVER_URL}/platform/api/all?page=1&page_size=1000\`)
        const apisList = Array.isArray(data) ? data : (data.apis || data.response?.apis || [])
        setExistingApis(apisList.map((a: any) => ({ api_name: a.api_name || a.name, api_version: a.api_version || a.version })))
      } catch (err) {
        console.error('Failed to load APIs', err)
      }
    }
    fetchApis()
  }, [])`;
code = code.replace(/const \[apiName, setApiName\] = useState\(''\)[\s\S]*?const \[apiVersion, setApiVersion\] = useState\('v1'\)/, stateInjection);

// 4. Update UI Section 2
const configUIRegex = /<div className="bg-white border-2 border-gray-900 shadow-\[4px_4px_0px_0px_rgba\(15,23,42,1\)\] p-6">[\s\S]*?<h2 className="text-lg font-bold text-gray-900 mb-4 uppercase tracking-wider">2. API Configuration<\/h2>[\s\S]*?<div className="grid grid-cols-1 md:grid-cols-2 gap-4">[\s\S]*?<div>[\s\S]*?<label className="block text-xs font-bold uppercase text-gray-600 mb-1">API Name<\/label>[\s\S]*?<input type="text" value=\{apiName\} onChange=\{e => setApiName\(e.target.value\)\} className="w-full border-2 border-gray-900 p-2" \/>[\s\S]*?<\/div>[\s\S]*?<div>[\s\S]*?<label className="block text-xs font-bold uppercase text-gray-600 mb-1">API Version<\/label>[\s\S]*?<input type="text" value=\{apiVersion\} onChange=\{e => setApiVersion\(e.target.value\)\} className="w-full border-2 border-gray-900 p-2" \/>[\s\S]*?<\/div>[\s\S]*?<\/div>[\s\S]*?<\/div>/;

const newConfigUI = `<div className="bg-white border-2 border-gray-900 shadow-[4px_4px_0px_0px_rgba(15,23,42,1)] p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-900 uppercase tracking-wider">2. API Target</h2>
              <div className="flex bg-gray-200 border-2 border-gray-900">
                <button onClick={() => setApiTargetMode('new')} className={\`px-4 py-1 text-xs font-bold uppercase \${apiTargetMode === 'new' ? 'bg-[#38bdf8] text-gray-900' : 'text-gray-600 hover:bg-gray-300'}\`}>Create New API</button>
                <button onClick={() => setApiTargetMode('existing')} className={\`px-4 py-1 text-xs font-bold uppercase border-l-2 border-gray-900 \${apiTargetMode === 'existing' ? 'bg-[#38bdf8] text-gray-900' : 'text-gray-600 hover:bg-gray-300'}\`}>Append to Existing</button>
              </div>
            </div>
            
            {apiTargetMode === 'new' ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">New API Name</label>
                  <input type="text" value={apiName} onChange={e => setApiName(e.target.value)} className="w-full border-2 border-gray-900 p-2 focus:outline-none focus:ring-2 focus:ring-[#38bdf8]" />
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">New API Version</label>
                  <input type="text" value={apiVersion} onChange={e => setApiVersion(e.target.value)} className="w-full border-2 border-gray-900 p-2 focus:outline-none focus:ring-2 focus:ring-[#38bdf8]" />
                </div>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Select Existing API</label>
                <select 
                  className="w-full border-2 border-gray-900 p-2 focus:outline-none focus:ring-2 focus:ring-[#38bdf8]"
                  value={\`\${apiName}::\${apiVersion}\`}
                  onChange={(e) => {
                    const [n, v] = e.target.value.split('::')
                    if (n && v) {
                      setApiName(n)
                      setApiVersion(v)
                    }
                  }}
                >
                  <option value="::" disabled>-- Select an API --</option>
                  {existingApis.map(a => (
                    <option key={\`\${a.api_name}::\${a.api_version}\`} value={\`\${a.api_name}::\${a.api_version}\`}>
                      {a.api_name} ({a.api_version})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>`;

code = code.replace(configUIRegex, newConfigUI);

// 5. Update publish function
const publishRegex = /const publish = async \(\) => \{[\s\S]*?try \{[\s\S]*?\/\/ 1\. Create or ensure API exists[\s\S]*?const apiPayload = \{[\s\S]*?api_name: apiName,[\s\S]*?api_version: apiVersion,[\s\S]*?api_description: \`Imported via Swagger\`,[\s\S]*?api_type: 'http',[\s\S]*?api_servers: bulkServer \? \[bulkServer\] : \[\][\s\S]*?\}[\s\S]*?try \{[\s\S]*?await postJson\(\`\$\{SERVER_URL\}\/platform\/api\`, apiPayload\)[\s\S]*?\} catch \(err: any\) \{[\s\S]*?if \(err\.message\.includes\('already exists'\)\) \{[\s\S]*?setShowAppendModal\(true\)[\s\S]*?setPublishing\(false\)[\s\S]*?return[\s\S]*?\} else \{[\s\S]*?throw new Error\('Failed to create API: ' \+ err\.message\)[\s\S]*?\}[\s\S]*?\}[\s\S]*?await createEndpoints\(\)[\s\S]*?\} catch \(err: any\) \{[\s\S]*?toast\.error\(err\.message\)[\s\S]*?setPublishing\(false\)[\s\S]*?\}[\s\S]*?\}/m;

const newPublishLogic = `const publish = async () => {
    if (!apiName || !apiVersion || (apiTargetMode === 'existing' && !existingApis.some(a => a.api_name === apiName && a.api_version === apiVersion))) {
      toast.error('Valid API Name and Version are required')
      return
    }
    
    const selectedEndpoints = endpoints.filter(e => e.selected)
    if (selectedEndpoints.length === 0) {
      toast.error('No endpoints selected to publish')
      return
    }

    setPublishing(true)
    try {
      if (apiTargetMode === 'new') {
        // 1. Create API
        const apiPayload = {
          api_name: apiName,
          api_version: apiVersion,
          api_description: \`Imported via Swagger\`,
          api_type: 'http',
          api_servers: bulkServer ? [bulkServer] : []
        }
        
        try {
          await postJson(\`\${SERVER_URL}/platform/api\`, apiPayload)
        } catch (err: any) {
          if (err.message.includes('already exists')) {
            setShowAppendModal(true)
            setPublishing(false)
            return
          } else {
            throw new Error('Failed to create API: ' + err.message)
          }
        }
      }
      
      // If we are in 'existing' mode or API creation succeeded
      await createEndpoints()
    } catch (err: any) {
      toast.error(err.message)
      setPublishing(false)
    }
  }`;
  
code = code.replace(publishRegex, newPublishLogic);

fs.writeFileSync(file, code);
