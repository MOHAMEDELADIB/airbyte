package io.airbyte.config.persistence;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;

import io.airbyte.commons.json.Jsons;
import io.airbyte.config.SourceConnection;
import io.airbyte.config.StandardSourceDefinition;
import io.airbyte.config.StandardSourceDefinition.SourceType;
import io.airbyte.config.StandardWorkspace;
import io.airbyte.config.persistence.split_secrets.MemorySecretPersistence;
import io.airbyte.config.persistence.split_secrets.NoOpSecretsHydrator;
import io.airbyte.db.Database;
import io.airbyte.db.instance.configs.ConfigsDatabaseInstance;
import io.airbyte.protocol.models.AirbyteCatalog;
import io.airbyte.protocol.models.ConnectorSpecification;
import io.airbyte.validation.json.JsonValidationException;
import java.io.IOException;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

public class ConfigRepositoryE2EReadWriteTest {
  protected static PostgreSQLContainer<?> container;
  protected static Database database;
  private ConfigRepository configRepository;
  protected static DatabaseConfigPersistence configPersistence;

  @BeforeAll
  public static void dbSetup() {
    container = new PostgreSQLContainer<>("postgres:13-alpine")
        .withDatabaseName("airbyte")
        .withUsername("docker")
        .withPassword("docker");
    container.start();
  }

  @BeforeEach
  void setup() throws IOException {
    database = mock(Database.class);
    final var secretPersistence = new MemorySecretPersistence();
    configPersistence = spy(new DatabaseConfigPersistence(database));
    configRepository =
        spy(new ConfigRepository(configPersistence, new NoOpSecretsHydrator(), Optional.of(secretPersistence), Optional.of(secretPersistence),
            database));
    database = new ConfigsDatabaseInstance(container.getUsername(), container.getPassword(), container.getJdbcUrl()).getAndInitialize();
  }

  @AfterAll
  public static void dbDown() {
    container.close();
  }

  @Test
  void testInsertActorCatalog() throws IOException, JsonValidationException {

    final StandardWorkspace workspace = new StandardWorkspace()
        .withWorkspaceId(UUID.randomUUID())
        .withName("Default workspace");
    configRepository.writeStandardWorkspace(workspace);

    final StandardSourceDefinition sourceDefinition = new StandardSourceDefinition()
        .withSourceDefinitionId(UUID.randomUUID())
        .withSourceType(SourceType.DATABASE)
        .withDockerRepository("docker-repo")
        .withDockerImageTag("1.2.0");
    configRepository.writeStandardSourceDefinition(sourceDefinition);

    final SourceConnection source = new SourceConnection()
        .withSourceDefinitionId(sourceDefinition.getSourceDefinitionId())
        .withSourceId(UUID.randomUUID())
        .withName("SomeConnector")
        .withWorkspaceId(workspace.getWorkspaceId())
        .withConfiguration(Jsons.deserialize("{}"));
    final ConnectorSpecification specification = new ConnectorSpecification()
        .withConnectionSpecification(Jsons.deserialize("{}"));
    final SourceConnection sourceConnection = new SourceConnection()
        .withSourceId(UUID.randomUUID())
        .withSourceDefinitionId(UUID.randomUUID())
        .withName("")
        .withConfiguration(Jsons.deserialize("{}"))
        .withWorkspaceId(workspace.getWorkspaceId());
    configRepository.writeSourceConnection(sourceConnection, specification);

    final AirbyteCatalog actorCatalog = new AirbyteCatalog();
    configRepository.writeActorCatalogFetchEvent(
        actorCatalog, source.getSourceId(), "", "1.2.0");

    final Optional<AirbyteCatalog> catalog =
        configRepository.getActorCatalog(source.getSourceId(), "1.2.0", "ConfigHash");
    assertTrue(catalog.isPresent());
    assertEquals(actorCatalog, catalog.get());
  }

}
