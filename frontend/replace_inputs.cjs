const fs = require('fs');
const path = require('path');

function walkDir(dir, callback) {
  fs.readdirSync(dir).forEach(f => {
    let dirPath = path.join(dir, f);
    let isDirectory = fs.statSync(dirPath).isDirectory();
    isDirectory ? walkDir(dirPath, callback) : callback(path.join(dir, f));
  });
}

walkDir('/home/frappe/frappe-bench/apps/flamezo_backend/frontend/src', function(filePath) {
  if (filePath.endsWith('.tsx') && !filePath.endsWith('number-input.tsx')) {
    let content = fs.readFileSync(filePath, 'utf8');

    // If it uses NumberInput but doesn't import it
    if (content.includes('<NumberInput') && !content.includes('@/components/ui/number-input')) {
      if (content.includes('import { Input } from')) {
        content = content.replace(/import\s+\{\s*Input\s*\}\s+from\s+['"]@\/components\/ui\/input['"]/g, "import { Input } from \"@/components/ui/input\"\nimport { NumberInput } from \"@/components/ui/number-input\"");
      } else {
        content = "import { NumberInput } from \"@/components/ui/number-input\"\n" + content;
      }
      fs.writeFileSync(filePath, content, 'utf8');
      console.log('Added import to: ' + filePath);
    }
  }
});
