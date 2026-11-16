-- Arquivo: database/schema.sql
-- Função: cria o banco "wayhub" e todas as tabelas. Rode inteiro no MySQL Workbench (⚡).
-- ATENÇÃO: a linha abaixo APAGA o banco wayhub antigo (e seus dados) para recriar do zero.
SET NAMES utf8mb4;
DROP DATABASE IF EXISTS wayhub;
CREATE DATABASE wayhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE wayhub;

-- Login de todos os perfis
CREATE TABLE usuarios (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    tipo        ENUM('motorista','centro') NOT NULL,
    email       VARCHAR(150) NOT NULL UNIQUE,
    senha_hash  VARCHAR(200) NOT NULL,
    telefone    VARCHAR(15)  NOT NULL,
    criado_em   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE motoristas (
    usuario_id     INT PRIMARY KEY,
    nome           VARCHAR(80)  NOT NULL,
    sobrenome      VARCHAR(80)  NOT NULL,
    cidade_origem  VARCHAR(80)  NOT NULL,
    endereco       VARCHAR(200) NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE veiculos (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    motorista_id  INT NOT NULL UNIQUE,
    tipo          VARCHAR(30) NOT NULL,
    modelo        VARCHAR(80) NOT NULL,
    placa         CHAR(7)     NOT NULL UNIQUE,
    ano           SMALLINT    NOT NULL,
    FOREIGN KEY (motorista_id) REFERENCES motoristas(usuario_id) ON DELETE CASCADE
);

CREATE TABLE centros (
    usuario_id  INT PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    cnpj        CHAR(14)     NOT NULL UNIQUE,
    cidade      VARCHAR(80)  NOT NULL,
    bairro      VARCHAR(80)  NOT NULL,
    logradouro  VARCHAR(150) NOT NULL,
    numero      VARCHAR(15)  NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- Uma carona = um motorista levando pedidos de um centro para outro
CREATE TABLE caronas (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    motorista_id      INT NOT NULL,
    veiculo_id        INT NOT NULL,
    centro_origem_id  INT NOT NULL,
    centro_destino_id INT NOT NULL,
    codigo_retirada   CHAR(6) NOT NULL,
    codigo_entrega    CHAR(6) NULL,
    taxa_total        DECIMAL(8,2) NOT NULL,
    status            ENUM('solicitada','em_andamento','encerrada','cancelada') NOT NULL DEFAULT 'solicitada',
    retirada_prevista DATETIME NOT NULL,
    solicitada_em     DATETIME NOT NULL,
    retirada_em       DATETIME NULL,
    entrega_em        DATETIME NULL,
    FOREIGN KEY (motorista_id)      REFERENCES motoristas(usuario_id),
    FOREIGN KEY (veiculo_id)        REFERENCES veiculos(id),
    FOREIGN KEY (centro_origem_id)  REFERENCES centros(usuario_id),
    FOREIGN KEY (centro_destino_id) REFERENCES centros(usuario_id),
    INDEX idx_caronas_status (status)
);

-- Pedidos cadastrados pelos centros (retirado_em/entregue_em alimentam o treino da IA)
CREATE TABLE pedidos (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    codigo_pedido     VARCHAR(20) NOT NULL UNIQUE,
    seq_centro        INT NOT NULL,
    centro_origem_id  INT NOT NULL,
    centro_destino_id INT NOT NULL,
    descricao         VARCHAR(150) NOT NULL,
    altura_cm         DECIMAL(7,2) NOT NULL,
    comprimento_cm    DECIMAL(7,2) NOT NULL,
    largura_cm        DECIMAL(7,2) NOT NULL,
    peso_kg           DECIMAL(7,3) NOT NULL,
    categoria         VARCHAR(30)  NOT NULL,
    taxa              DECIMAL(8,2) NOT NULL,
    retirada_prevista DATETIME NOT NULL,
    status            ENUM('disponivel','solicitado','em_andamento','encerrado','cancelado') NOT NULL DEFAULT 'disponivel',
    carona_id         INT NULL,
    retirado_em       DATETIME NULL,
    entregue_em       DATETIME NULL,
    pago              BOOLEAN NOT NULL DEFAULT FALSE,
    pago_em           DATETIME NULL,
    criado_em         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_pedido_centro (centro_origem_id, seq_centro),
    FOREIGN KEY (centro_origem_id)  REFERENCES centros(usuario_id),
    FOREIGN KEY (centro_destino_id) REFERENCES centros(usuario_id),
    FOREIGN KEY (carona_id)         REFERENCES caronas(id) ON DELETE SET NULL,
    INDEX idx_pedidos_status (status, retirada_prevista)
);

-- Base de treino da IA: entregas já realizadas (você alimenta com INSERT ou importando um CSV pelo Workbench).
-- O sistema junta esta tabela com os pedidos encerrados do WayHub para treinar a IA ao iniciar.
CREATE TABLE historico_entregas (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    cidade_origem   VARCHAR(80)  NOT NULL,
    cidade_destino  VARCHAR(80)  NOT NULL,
    distancia_km    DECIMAL(8,1) NULL,          -- pode ficar NULL: o sistema estima pela localização das cidades
    peso_kg         DECIMAL(7,3) NOT NULL,
    altura_cm       DECIMAL(7,2) NOT NULL,
    comprimento_cm  DECIMAL(7,2) NOT NULL,
    largura_cm      DECIMAL(7,2) NOT NULL,
    retirado_em     DATETIME NOT NULL,
    entregue_em     DATETIME NOT NULL
);
