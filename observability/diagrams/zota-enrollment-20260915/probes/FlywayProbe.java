import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.flywaydb.core.Flyway;

// Runs against in-memory H2 only. Never uses a deployed database.
public class FlywayProbe {
    public static void main(String[] args) throws Exception {
        Path migrations = Path.of(args[0]).toAbsolutePath();
        Path oldOnly = Files.createTempDirectory("zota-old-baseline-");
        Files.copy(migrations.resolve("B1_20_0__1.0.0_baseline__H2.sql"),
                oldOnly.resolve("B1_20_0__1.0.0_baseline__H2.sql"));
        String fresh = "jdbc:h2:mem:enrollment_fresh;DB_CLOSE_DELAY=-1";
        String existing = "jdbc:h2:mem:enrollment_existing;DB_CLOSE_DELAY=-1";
        migrate(fresh, migrations);
        describe("FRESH", fresh);
        migrate(existing, oldOnly);
        migrate(existing, migrations);
        describe("EXISTING", existing);
    }

    static void migrate(String url, Path dir) {
        Flyway.configure().dataSource(url, "sa", "")
                .table("schema_version").sqlMigrationSuffixes("H2.sql")
                .locations("filesystem:" + dir).load().migrate();
    }

    static void describe(String scenario, String url) throws Exception {
        try (var c = DriverManager.getConnection(url, "sa", "");
             var s = c.createStatement()) {
            for (String table : new String[]{"SP_TARGET", "SP_TARGET_ENROLLMENT_TOKEN",
                    "SP_TARGET_ENROLLMENT_ISSUANCE"}) {
                try (var r = s.executeQuery("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES"
                        + " WHERE TABLE_SCHEMA='PUBLIC' AND TABLE_NAME='" + table + "'")) {
                    r.next();
                    System.out.println("PROBE " + scenario + " " + table + "=" + r.getInt(1));
                }
            }
        }
    }
}
