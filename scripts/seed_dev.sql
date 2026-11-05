-- Dados de teste para o ambiente local. Pode rodar mais de uma vez.
--
-- A API tem duas tabelas de itens que não se ligam:
--   GET /menu/list lê menu_items; POST /orders procura o produto em produto.
-- Por isso, cada item é inserido nas duas com o MESMO id, a partir de uma única lista.

BEGIN;

CREATE TEMP TABLE seed_item (
    id        bigint,
    categoria bigint,
    tipo      text,
    nome      text,
    descricao text,
    preco     numeric(10, 2),
    ativo     boolean
) ON COMMIT DROP;

INSERT INTO seed_item VALUES
    (1,  1, 'PIZZA', 'Pizza Calabresa Média',       'Calabresa, cebola e muçarela',              42.00, true),
    (2,  1, 'PIZZA', 'Pizza Calabresa Grande',      'Calabresa, cebola e muçarela',              55.00, true),
    (3,  1, 'PIZZA', 'Pizza Marguerita Média',      'Tomate, manjericão e muçarela',             40.00, true),
    (4,  1, 'PIZZA', 'Pizza Marguerita Grande',     'Tomate, manjericão e muçarela',             52.00, true),
    (5,  1, 'PIZZA', 'Pizza Portuguesa Média',      'Presunto, ovo, cebola, azeitona e muçarela', 45.00, true),
    (6,  1, 'PIZZA', 'Pizza Portuguesa Grande',     'Presunto, ovo, cebola, azeitona e muçarela', 58.00, true),
    (7,  1, 'PIZZA', 'Pizza Quatro Queijos Grande', 'Indisponível, para testar esse caso',        60.00, false),
    (8,  2, 'DRINK', 'Refrigerante Lata',           'Lata de 350 ml',                             7.00, true),
    (9,  2, 'DRINK', 'Água sem Gás',                'Garrafa de 500 ml',                          5.00, true),
    (10, 2, 'DRINK', 'Suco de Laranja',             'Copo de 400 ml',                            10.00, true);

INSERT INTO categoria (id, empresa_id, nome) VALUES
    (1, '550e8400-e29b-41d4-a716-446655440000', 'Pizzas'),
    (2, '550e8400-e29b-41d4-a716-446655440000', 'Bebidas')
ON CONFLICT (id) DO NOTHING;

INSERT INTO produto (id, empresa_id, categoria_id, nome, preco, descricao, disponivel, criado_em, atualizado_em)
SELECT id, '550e8400-e29b-41d4-a716-446655440000', categoria, nome, preco, descricao, ativo, now(), now()
FROM seed_item
ON CONFLICT (id) DO UPDATE SET
    nome = EXCLUDED.nome,
    preco = EXCLUDED.preco,
    descricao = EXCLUDED.descricao,
    disponivel = EXCLUDED.disponivel,
    atualizado_em = now();

INSERT INTO menu_items (id, name, description, category, price, available)
SELECT id, nome, descricao, tipo, preco, ativo
FROM seed_item
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    price = EXCLUDED.price,
    available = EXCLUDED.available;

INSERT INTO tb_tables (id, company_id, table_number, access_code, status, created_at, updated_at)
SELECT numero, '550e8400-e29b-41d4-a716-446655440000', numero, gen_random_uuid(), 'FREE', now(), now()
FROM generate_series(1, 5) AS numero
ON CONFLICT (id) DO NOTHING;

-- Como os ids foram informados à mão, as sequências precisam avançar para evitar conflito depois.
SELECT setval(pg_get_serial_sequence('categoria', 'id'), (SELECT max(id) FROM categoria));
SELECT setval(pg_get_serial_sequence('produto', 'id'), (SELECT max(id) FROM produto));
SELECT setval(pg_get_serial_sequence('menu_items', 'id'), (SELECT max(id) FROM menu_items));
SELECT setval(pg_get_serial_sequence('tb_tables', 'id'), (SELECT max(id) FROM tb_tables));

COMMIT;
