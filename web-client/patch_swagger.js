const fs = require('fs');
const file = 'src/app/apis/import-swagger/page.tsx';
let code = fs.readFileSync(file, 'utf8');

// Add import for ConfirmModal
code = code.replace(
  "import toast from 'react-hot-toast'",
  "import toast from 'react-hot-toast'\nimport ConfirmModal from '@/components/ConfirmModal'"
);

// Add showAppendModal state
code = code.replace(
  "const [publishing, setPublishing] = useState(false)",
  "const [publishing, setPublishing] = useState(false)\n  const [showAppendModal, setShowAppendModal] = useState(false)"
);

// Replace publish method and add createEndpoints
const publishRegex = /const publish = async \(\) => \{[\s\S]*?try \{[\s\S]*?\/\/ 2\. Create endpoints[\s\S]*?\} catch \(err: any\) \{[\s\S]*?toast\.error\(err\.message\)[\s\S]*?\} finally \{[\s\S]*?setPublishing\(false\)[\s\S]*?\}[\s\S]*?\}/m;

const newPublishCode = `const createEndpoints = async () => {
    setPublishing(true)
    setShowAppendModal(false)
    const selectedEndpoints = endpoints.filter(e => e.selected)
    try {
      // 2. Create endpoints
      for (const ep of selectedEndpoints) {
        const epPayload = {
          api_name: apiName,
          api_version: apiVersion,
          endpoint_method: ep.method,
          endpoint_uri: ep.path,
          auth_required: ep.auth_required,
          rate_limit: ep.rate_limit,
          endpoint_servers: ep.upstream_server ? [ep.upstream_server] : []
        }
        await postJson(\`\${SERVER_URL}/platform/endpoint\`, epPayload)
      }
      
      toast.success(\`Published \${selectedEndpoints.length} endpoints successfully!\`)
      router.push(\`/apis/\${apiName}:\${apiVersion}\`)
      
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setPublishing(false)
    }
  }

  const publish = async () => {
    if (!apiName || !apiVersion) {
      toast.error('API Name and Version are required')
      return
    }
    
    const selectedEndpoints = endpoints.filter(e => e.selected)
    if (selectedEndpoints.length === 0) {
      toast.error('No endpoints selected to publish')
      return
    }

    setPublishing(true)
    try {
      // 1. Create or ensure API exists
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
      
      await createEndpoints()
    } catch (err: any) {
      toast.error(err.message)
      setPublishing(false)
    }
  }`;

code = code.replace(publishRegex, newPublishCode);

// Add modal before </Layout>
const modalCode = `      <ConfirmModal
        open={showAppendModal}
        title="API Already Exists"
        message={
          <div>
            <p className="mb-2">The API <code className="font-mono bg-gray-100 px-1">{apiName} ({apiVersion})</code> already exists in Doorman.</p>
            <p>Do you want to append these endpoints to the existing API?</p>
          </div>
        }
        confirmLabel="Append Endpoints"
        onConfirm={createEndpoints}
        onCancel={() => setShowAppendModal(false)}
      />
    </Layout>
`;
code = code.replace("</Layout>", modalCode);

fs.writeFileSync(file, code);
