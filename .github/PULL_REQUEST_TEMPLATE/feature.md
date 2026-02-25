## Descrição
<!-- O que foi implementado? Nova opção de migração, suporte a novo formato, melhoria de performance? -->


## Motivação e contexto
<!-- Por que esta mudança é necessária? -->


## Checklist

### Código
- [ ] Lint passou sem erros (`ruff check .`)
- [ ] Testes foram criados ou atualizados (`pytest`)
- [ ] Sem credenciais, tokens ou dados de pacientes no código

### Migração e compatibilidade
- [ ] Testado com arquivo `EPWinData.mdb` real
- [ ] Testado com arquivo `BLPatients.mdb` real
- [ ] Schema MySQL gerado é compatível com o existente (sem breaking changes)
- [ ] Hierarquia pacientes → sessões → exames preservada corretamente
- [ ] Testado com Docker (`python migrate.py ... --docker`)
- [ ] Testado com MySQL nativo (se aplicável)

### Plataformas
- [ ] Testado no Linux/macOS
- [ ] Testado no Windows (se possível)

### Branch
- [ ] Branch de origem: `develop`
- [ ] PR apontando para: `develop`

## Como testar
<!-- Inclua o comando exato usado para testar -->
```bash
python migrate.py "caminho/EPWinData.mdb" "caminho/BLPatients.mdb" --docker
```

## Issues relacionadas
Closes #
