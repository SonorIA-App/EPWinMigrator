## Descrição do bug
<!-- Qual era o comportamento incorreto durante a migração? -->


## Causa raiz
<!-- O que causava o problema? Ex: decodificação incorreta, query SQL errada, campo ignorado -->


## Solução aplicada
<!-- Como o bug foi corrigido? -->


## Checklist

### Código
- [ ] Lint passou sem erros (`ruff check .`)
- [ ] Teste de regressão criado para cobrir o caso do bug (`pytest`)
- [ ] Sem credenciais ou dados de pacientes no código

### Migração e compatibilidade
- [ ] Correto com `EPWinData.mdb` e `BLPatients.mdb` reais
- [ ] Dados migrados conferidos manualmente no MySQL após a correção
- [ ] Correção não afeta dados já migrados corretamente

### Branch
- [ ] Branch de origem: `develop`
- [ ] PR apontando para: `develop`

## Como reproduzir o bug (antes da correção)
1.
2.

## Como verificar a correção
```bash
python migrate.py "caminho/EPWinData.mdb" "caminho/BLPatients.mdb" --docker
```

## Issues relacionadas
Closes #
