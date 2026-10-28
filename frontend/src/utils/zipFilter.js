import JSZip from 'jszip';

// Smart bloat directories and extensions to skip
// Exact segment matching prevents false positives on 'src/env/config.js' or 'lib/vendor/helper.js'
export const IGNORED_DIRECTORIES = new Set([
  'node_modules', '.venv', 'venv', 'target', 'build',
  'dist', '.git', '.idea', '.vscode', '__pycache__', '.next'
]);

export const IGNORED_EXTENSIONS = [
  '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.tar', '.gz',
  '.exe', '.dll', '.so', '.dylib', '.jar', '.iso', '.mp4', '.mov', '.ico', '.svg'
];

/**
 * Strips node_modules, .venv, binaries, and build artifacts directly in the browser.
 * Reduces a 500 MB - 1 GB upload down to ~2 MB of pure source code in seconds.
 *
 * @param {File} rawFile - The raw user-selected .zip file
 * @param {Function} [onProgress] - Optional callback receiving progress text
 * @returns {Promise<{ cleanFile: File, originalSizeMB: string, cleanSizeMB: string, skippedFiles: number, totalFiles: number, savedPercent: string }>}
 */
export async function preFilterProjectZip(rawFile, onProgress) {
  const originalBytes = rawFile.size;
  const originalSizeMB = (originalBytes / (1024 * 1024)).toFixed(1);
  if (onProgress) onProgress(`Loading raw ZIP archive (${originalSizeMB} MB)...`);

  const zip = await JSZip.loadAsync(rawFile);
  const cleanZip = new JSZip();

  let totalFiles = 0;
  let skippedFiles = 0;

  const entries = Object.keys(zip.files);
  const totalEntries = entries.length;

  for (let i = 0; i < totalEntries; i++) {
    const relativePath = entries[i];
    const zipEntry = zip.files[relativePath];

    // Skip directories themselves
    if (zipEntry.dir) continue;

    totalFiles++;

    // Normalize path separators to forward slashes
    const normalizedPath = relativePath.replace(/\\/g, '/');
    const segments = normalizedPath.toLowerCase().split('/');
    const dirSegments = segments.slice(0, -1);

    // 1. Check if path is inside ignored dependency or build directories (exact folder segment match)
    const isIgnoredDir = dirSegments.some(seg => IGNORED_DIRECTORIES.has(seg));

    // 2. Check for binary or asset extensions
    const isIgnoredExt = IGNORED_EXTENSIONS.some(ext =>
      normalizedPath.toLowerCase().endsWith(ext.toLowerCase())
    );

    if (isIgnoredDir || isIgnoredExt) {
      skippedFiles++;
      continue;
    }

    // Extract file bytes and add to clean ZIP
    const fileData = await zipEntry.async('uint8array');
    cleanZip.file(relativePath, fileData);
  }

  if (totalFiles > 0 && totalFiles === skippedFiles) {
    throw new Error('All files in the archive are ignored dependencies or binaries. No source code files found to index.');
  }

  if (onProgress) onProgress(`Generating clean source archive (Filtered ${skippedFiles} bloat files)...`);

  const cleanBlob = await cleanZip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 }
  });

  const cleanBytes = cleanBlob.size;
  const cleanSizeMB = (cleanBytes / (1024 * 1024)).toFixed(2);

  // Compute saved bandwidth safely avoiding division by zero
  const savedPercent = originalBytes > cleanBytes && originalBytes > 0
    ? Math.max(0, Math.min(99.9, ((1 - cleanBytes / originalBytes) * 100))).toFixed(1)
    : '0.0';

  return {
    cleanFile: new File([cleanBlob], rawFile.name, { type: 'application/zip' }),
    originalSizeMB,
    cleanSizeMB,
    skippedFiles,
    totalFiles,
    savedPercent
  };
}

/**
 * Takes a raw FileList or File[] from folder selection/drop, applies segment matching
 * and extension rules, and packs pure source files into an in-memory JSZip.
 *
 * @param {FileList|File[]} fileList - Raw files from webkitdirectory or folder drop
 * @param {Function} [onProgress] - Optional callback receiving stage updates
 * @returns {Promise<{ cleanFile: File, originalSizeMB: string, cleanSizeMB: string, skippedFiles: number, totalFiles: number, savedPercent: string }>}
 */
export async function filterAndZipFolder(fileList, onProgress) {
  const cleanZip = new JSZip();
  let totalFiles = 0;
  let skippedFiles = 0;
  let totalBytes = 0;

  const filesArray = Array.from(fileList);
  const totalEntries = filesArray.length;

  if (onProgress) onProgress(`Scanning ${totalEntries} local files...`);

  for (let i = 0; i < totalEntries; i++) {
    const file = filesArray[i];
    const relativePath = file.webkitRelativePath || file.name;
    const normalizedPath = relativePath.replace(/\\/g, '/');
    const segments = normalizedPath.toLowerCase().split('/');
    const dirSegments = segments.slice(0, -1);

    totalFiles++;
    totalBytes += file.size || 0;

    // Exact directory segment check
    const isIgnoredDir = dirSegments.some(seg => IGNORED_DIRECTORIES.has(seg));
    // Extension check
    const isIgnoredExt = IGNORED_EXTENSIONS.some(ext =>
      normalizedPath.toLowerCase().endsWith(ext.toLowerCase())
    );

    if (isIgnoredDir || isIgnoredExt) {
      skippedFiles++;
      continue;
    }

    cleanZip.file(relativePath, file);
  }

  if (totalFiles > 0 && totalFiles === skippedFiles) {
    throw new Error('Selected folder contains only ignored dependencies or binary files. No indexable source code found.');
  }

  const originalSizeMB = (totalBytes / (1024 * 1024)).toFixed(1);
  if (onProgress) onProgress(`Compressing ${totalFiles - skippedFiles} clean source files (${originalSizeMB} MB raw)...`);

  const cleanBlob = await cleanZip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 }
  });

  const cleanBytes = cleanBlob.size;
  const cleanSizeMB = (cleanBytes / (1024 * 1024)).toFixed(2);
  const savedPercent = totalBytes > cleanBytes && totalBytes > 0
    ? Math.max(0, Math.min(99.9, ((1 - cleanBytes / totalBytes) * 100))).toFixed(1)
    : '0.0';

  const folderName = filesArray[0]?.webkitRelativePath?.split('/')[0] || 'local-project';

  return {
    cleanFile: new File([cleanBlob], `${folderName}.zip`, { type: 'application/zip' }),
    originalSizeMB,
    cleanSizeMB,
    skippedFiles,
    totalFiles,
    savedPercent
  };
}

/**
 * Recursively extracts files from a DataTransferItemList when a folder or files are dropped.
 * Supports FileSystemEntry API (webkitGetAsEntry) and handles chunked DirectoryReader.
 *
 * @param {DataTransfer} dataTransfer
 * @returns {Promise<File[]>} Array of File objects with .webkitRelativePath set
 */
export async function getFilesFromDataTransfer(dataTransfer) {
  const items = dataTransfer.items;
  if (!items || items.length === 0) {
    return Array.from(dataTransfer.files || []);
  }

  const files = [];

  async function traverseEntry(entry, path = '') {
    if (entry.isFile) {
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      const relPath = path ? `${path}${file.name}` : file.name;
      Object.defineProperty(file, 'webkitRelativePath', {
        value: relPath,
        writable: true,
        configurable: true
      });
      files.push(file);
    } else if (entry.isDirectory) {
      const dirReader = entry.createReader();
      const readAllEntries = async () => {
        const batch = await new Promise((resolve, reject) => dirReader.readEntries(resolve, reject));
        if (batch && batch.length > 0) {
          for (const child of batch) {
            await traverseEntry(child, `${path}${entry.name}/`);
          }
          await readAllEntries(); // Read next chunk (readEntries returns in slices up to 100)
        }
      };
      await readAllEntries();
    }
  }

  const traversePromises = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.webkitGetAsEntry) {
      const entry = item.webkitGetAsEntry();
      if (entry) {
        traversePromises.push(traverseEntry(entry));
        continue;
      }
    }
    const file = item.getAsFile ? item.getAsFile() : null;
    if (file) files.push(file);
  }

  if (traversePromises.length > 0) {
    await Promise.all(traversePromises);
  }

  return files.length > 0 ? files : Array.from(dataTransfer.files || []);
}
