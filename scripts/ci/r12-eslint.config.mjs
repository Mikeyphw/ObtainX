export default [{
    files: ['**/*.mjs'],
    languageOptions: {ecmaVersion: 'latest', sourceType: 'module', globals: {console: 'readonly', process: 'readonly', URL: 'readonly'}},
    rules: {'no-undef': 'error', 'no-unused-vars': 'error', 'no-unreachable': 'error', 'no-dupe-keys': 'error', 'no-constant-condition': 'error', 'no-redeclare': 'error'},
}]
